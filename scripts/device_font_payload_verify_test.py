#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "common"))

import device_font_payload_verify as verifier


def payload(filename: str, size: int) -> dict:
    signature = "a" * 64
    return {
        "schema": "device-font-payload-v1",
        "summary": {
            "mapped": 1,
            "uniqueFonts": 1,
            "unsafe": 0,
            "unresolved": 0,
            "failures": 0,
        },
        "generated": [
            {
                "signature": signature,
                "filename": filename,
                "path": f"fonts/{filename}",
                "bytes": size,
            }
        ],
        "slots": [
            {
                "family": "sans-serif",
                "planStatus": "ready",
                "generatedFile": filename,
            }
        ],
    }


def expect_error(callable_, needle: str) -> None:
    try:
        callable_()
    except verifier.VerifyError as exc:
        assert needle in str(exc), str(exc)
    else:
        raise AssertionError(f"expected VerifyError containing {needle!r}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="luoshu-payload-verify-") as temp_raw:
        temp = Path(temp_raw)
        fonts = temp / "fonts"
        fonts.mkdir()
        font = fonts / "LuoShuSlot-test-400.ttf"
        font.write_bytes(b"\0" * 2048)
        manifest = payload(font.name, font.stat().st_size)
        (temp / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        result = verifier.verify(manifest, temp, strict=True)
        assert result["mapped"] == 1
        assert result["uniqueFonts"] == 1
        assert result["bytes"] == 2048
        assert len(result["manifestSha256"]) == 64

        broken_size = payload(font.name, 4096)
        expect_error(lambda: verifier.verify(broken_size, temp, strict=False), "大小不匹配")

        unknown_reference = payload(font.name, 2048)
        unknown_reference["slots"][0]["generatedFile"] = "missing.ttf"
        expect_error(lambda: verifier.verify(unknown_reference, temp, strict=False), "未知字体")

        unsafe = payload(font.name, 2048)
        unsafe["summary"]["unsafe"] = 1
        expect_error(lambda: verifier.verify(unsafe, temp, strict=True), "严格门禁拒绝")
        non_strict = verifier.verify(unsafe, temp, strict=False)
        assert non_strict["unsafe"] == 1

        traversal = payload(font.name, 2048)
        traversal["generated"][0]["path"] = "../outside.ttf"
        expect_error(lambda: verifier.verify(traversal, temp, strict=False), "非法负载路径")

    print("device font payload verifier tests passed")


if __name__ == "__main__":
    main()
