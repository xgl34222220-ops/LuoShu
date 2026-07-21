#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    replace_once(
        "common/font_config_overlay.py",
        '''PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono", "serif",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS
''',
        '''PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
# serif is protected at the file level, but cannot be a family substring token because the canonical
# Android UI family is literally named sans-serif.
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS + ("serif",)
''',
    )
    replace_once(
        "common/font_config_targets.py",
        '''PROTECTED_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono", "serif",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
''',
        '''PROTECTED_FAMILY_TOKENS = (
    "emoji", "symbol", "icon", "material", "dingbat", "mono",
    "clock", "mitype", "math", "music", "braille", "barcode", "qrcode",
    "fallback", "legacy",
)
PROTECTED_FILE_TOKENS = PROTECTED_FAMILY_TOKENS + ("serif",)
''',
    )
    replace_once(
        "common/font_config_targets.py",
        '    if not name or any(token in name for token in PROTECTED_TOKENS):\n',
        '    if not name or any(token in name for token in PROTECTED_FAMILY_TOKENS):\n',
    )
    replace_once(
        "common/font_config_targets.py",
        '        or any(token in filename for token in PROTECTED_TOKENS)\n',
        '        or any(token in filename for token in PROTECTED_FILE_TOKENS)\n',
    )
    runpy.run_path("scripts/finish_meta_font_safety_refactor_v3.py", run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
