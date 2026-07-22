#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[1]
patcher = root / "scripts/apply_import_mix_finalize_hotfix.py"
text = patcher.read_text(encoding="utf-8")
old = '''replace_once(
    "common/font_safety.sh",
    """                _lpm_sum=$(_luoshu_checksum \\"$_lpm_file\\")\\n""",
    """                _lpm_sum=$(_luoshu_cached_checksum \\"$_lpm_file\\" \\"$_lpm_checksum_cache\\")\\n""",
)
# The XML checksum line is the second identical occurrence after the first replacement.
replace_once(
    "common/font_safety.sh",
    """                _lpm_sum=$(_luoshu_checksum \\"$_lpm_file\\")\\n""",
    """                _lpm_sum=$(_luoshu_cached_checksum \\"$_lpm_file\\" \\"$_lpm_checksum_cache\\")\\n""",
)
'''
new = '''target = ROOT / "common/font_safety.sh"
checksum_text = target.read_text(encoding="utf-8")
checksum_old = "                _lpm_sum=$(_luoshu_checksum \\\"$_lpm_file\\\")\\n"
checksum_new = "                _lpm_sum=$(_luoshu_cached_checksum \\\"$_lpm_file\\\" \\\"$_lpm_checksum_cache\\\")\\n"
if checksum_text.count(checksum_old) != 2:
    raise SystemExit(f"common/font_safety.sh: expected two checksum sites, found {checksum_text.count(checksum_old)}")
target.write_text(checksum_text.replace(checksum_old, checksum_new), encoding="utf-8")
'''
if text.count(old) != 1:
    raise SystemExit("Unable to repair checksum replacement block")
patcher.write_text(text.replace(old, new, 1), encoding="utf-8")
runpy.run_path(str(patcher), run_name="__main__")
Path(__file__).unlink(missing_ok=True)
