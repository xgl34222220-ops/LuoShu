#!/usr/bin/env python3
"""Coverage parsing and unchanged runtime capability thresholds (host only)."""

import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "common/font_coverage_fields.py"
spec = importlib.util.spec_from_file_location("coverage_fields", PARSER)
fields = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fields)
VALID = {
    "safe": True, "face": 0, "faces": 1, "coreHan": 20992,
    "minimumCoreHan": 6000,
    "coverage": {"cjk": 100, "latin": 100, "digits": 100, "punctuation": 100},
    "message": "字形覆盖通过：核心汉字 20992 个",
}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


class CoverageFieldsTests(unittest.TestCase):
    def test_actual_android_analysis_response(self):
        self.assertEqual((20992, 100, 100, 100, 100), fields.parse_fields(encoded(VALID)))

    def test_pretty_unicode_and_escaped_keys(self):
        raw = json.dumps(VALID, ensure_ascii=True, indent=2).replace('"coreHan"', '"core\\u0048an"')
        self.assertEqual((20992, 100, 100, 100, 100), fields.parse_fields(raw.encode()))

    def test_embedded_and_unrelated_names_cannot_override(self):
        value = copy.deepcopy(VALID)
        value["message"] = '伪字段 "coreHan":0,"cjk":0 \\ \n'
        value["extra"] = {"coreHan": 0, "coverage": {"cjk": 0}}
        value["cjk"] = 0
        self.assertEqual((20992, 100, 100, 100, 100), fields.parse_fields(encoded(value)))

    def test_missing_required_fields(self):
        for key in ("coreHan", "coverage"):
            value = copy.deepcopy(VALID); del value[key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                fields.parse_fields(encoded(value))
        for key in fields.COVERAGE_FIELDS:
            value = copy.deepcopy(VALID); del value["coverage"][key]
            # A same-named diagnostic must never supply a missing coverage field.
            value[key] = 100; value["message"] = f'"{key}":100'
            with self.subTest(key=key), self.assertRaises(ValueError):
                fields.parse_fields(encoded(value))

    def test_rejects_wrong_types_and_out_of_range(self):
        for bad in (True, False, None, "100", 100.0, -1, 101, [], {}):
            value = copy.deepcopy(VALID); value["coverage"]["cjk"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                fields.parse_fields(encoded(value))
        for bad in (True, 0x110001, -1, "20992", 20992.0):
            value = copy.deepcopy(VALID); value["coreHan"] = bad
            with self.subTest(han=bad), self.assertRaises(ValueError):
                fields.parse_fields(encoded(value))

    def test_rejects_invalid_and_duplicate_json(self):
        raw = encoded(VALID)
        bad_inputs = (b'', b'[]', b'null', b'{', raw + b'{}',
                      raw.replace(b'"coreHan":20992', b'"coreHan":0,"coreHan":20992'),
                      raw.replace(b'"cjk":100', b'"cjk":0,"cjk":100'),
                      raw.replace(b'"cjk":100', b'"cjk":NaN'),
                      raw.replace(b'"cjk":100', b'"cjk":Infinity'),
                      raw.replace(b'"message":', b'"message":"\xff","other":'))
        for raw in bad_inputs:
            with self.subTest(raw=raw), self.assertRaises((ValueError, UnicodeError)):
                fields.parse_fields(raw)

    def test_partial_font_safe_false_is_not_a_rejection(self):
        value = copy.deepcopy(VALID)
        value["safe"] = False; value["coreHan"] = 0; value["coverage"]["cjk"] = 0
        self.assertEqual((0, 0, 100, 100, 100), fields.parse_fields(encoded(value)))

    def test_cli_is_bounded_and_never_emits_partial_fields(self):
        for raw in (b' ' * (fields.MAX_INPUT_BYTES + 1), b'{', b'[' * 2000):
            process = subprocess.run([sys.executable, str(PARSER)], input=raw, capture_output=True)
            self.assertEqual(2, process.returncode)
            self.assertEqual(b'', process.stdout)
            self.assertIn(b'Invalid font coverage response', process.stderr)
        process = subprocess.run([sys.executable, str(PARSER)], input=encoded(VALID), capture_output=True)
        self.assertEqual((0, b'20992 100 100 100 100\n', b''),
                         (process.returncode, process.stdout, process.stderr))


class RuntimePolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.module = Path(self.temp.name)
        common = self.module / "common"
        (common / "python/bin").mkdir(parents=True)
        (common / "font_coverage_fields.py").write_bytes(PARSER.read_bytes())
        (common / "font_coverage.py").write_text(
            "from pathlib import Path\nimport sys\n"
            "sys.stdout.buffer.write(Path(sys.argv[1]).read_bytes())\n")
        launcher = common / "python/bin/luoshu-python"
        launcher.write_text("#!/bin/sh\nunset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH\n"
                            "exec " + shlex.quote(sys.executable) + ' "$@"\n')
        launcher.chmod(0o755)
        self.script = '''
MODULE_DIR="$1"; MODDIR="$1"
. "$2/common/font_runtime_policy.sh"
font_validate() {
    FONT_CHECK_FORMAT=TTF; FONT_CHECK_SIZE=43404; FONT_CHECK_VARIABLE=false
    FONT_CHECK_COLOR=false; FONT_CHECK_WARNING=''; FONT_CHECK_ERROR=''
    return 0
}
LUOSHU_FONT_HAS_CJK=true; LUOSHU_FONT_HAS_LATIN=true; LUOSHU_FONT_HAS_MIXED=true
font_validate_global "$3"
result=$?
printf '%s\\n' "$result" "$LUOSHU_FONT_HAS_CJK:$LUOSHU_FONT_HAS_LATIN:$LUOSHU_FONT_HAS_MIXED" "$FONT_CHECK_ERROR" "$FONT_CHECK_COVERAGE"
'''

    def run_policy(self, value):
        response = self.module / "response.json"
        response.write_bytes(value if isinstance(value, bytes) else encoded(value))
        process = subprocess.run(["sh", "-c", self.script, "test", str(self.module), str(ROOT), str(response)],
                                 capture_output=True, text=True, timeout=10, env=os.environ.copy())
        self.assertEqual(0, process.returncode, process.stderr)
        self.assertEqual("", process.stderr)
        return process.stdout.splitlines()

    def test_actual_100_percent_response_passes(self):
        result = self.run_policy(VALID)
        self.assertEqual(["0", "true:true:true", ""], result[:3])
        self.assertIn("核心汉字 20992 个、中文 100%、英文 100%、数字 100%、标点 100%", result[3])

    def test_unchanged_partial_coverage_thresholds(self):
        for han, cjk, latin, digits, expected in (
            (6000, 95, 89, 99, "true:false:false"),
            (5999, 95, 90, 100, "false:true:false"),
            (6000, 94, 90, 100, "false:true:false"),
            (6000, 95, 90, 100, "true:true:true"),
        ):
            value = copy.deepcopy(VALID); value["safe"] = False; value["coreHan"] = han
            value["coverage"] = dict(cjk=cjk, latin=latin, digits=digits, punctuation=0)
            with self.subTest(values=(han,cjk,latin,digits)):
                result = self.run_policy(value)
                self.assertEqual(["0", expected, ""], result[:3])

    def test_neither_capability_rejected(self):
        value = copy.deepcopy(VALID); value["coreHan"] = 5999
        value["coverage"]["digits"] = 99
        result = self.run_policy(value)
        self.assertEqual(["1", "false:false:false"], result[:2])
        self.assertIn("字体既不具备可用中文覆盖", result[2])

    def test_malformed_response_fails_closed_and_clears_prior_flags(self):
        for value in (b'{', b'{}', b'{"coreHan":20992,"coverage":{"cjk":100}}'):
            with self.subTest(value=value):
                result = self.run_policy(value)
                self.assertEqual(["1", "false:false:false", "字形覆盖分析结果无效"], result[:3])

    def test_missing_parser_fails_closed(self):
        (self.module / "common/font_coverage_fields.py").unlink()
        result = self.run_policy(VALID)
        self.assertEqual(["1", "false:false:false", "字形覆盖分析器不可用"], result[:3])


if __name__ == "__main__":
    unittest.main()
