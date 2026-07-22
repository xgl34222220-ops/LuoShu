#!/usr/bin/env python3
"""Finish one-shot consistency migration after generated source review."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

util = ROOT / "common/util_functions.sh"
text = util.read_text(encoding="utf-8")
text = text.replace("避免文件名/目录顺序导致 WebUI 标签顺序混乱。", "避免文件名/目录顺序导致原生 App 标签顺序混乱。")
util.write_text(text, encoding="utf-8")

font_import = ROOT / "common/font_import.sh"
text = font_import.read_text(encoding="utf-8")
text = text.replace("作为 WebUI 显示名称", "作为原生 App 显示名称")
font_import.write_text(text, encoding="utf-8")

# Keep v1 cache cleanup only in the dedicated module-update migration path.
for path in (ROOT / "common").iterdir():
    if not path.is_file() or path.name == "module_update_state.sh" or path.parent.name == "python":
        continue
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    if "WebUI" in value or "webui_font_list" in value:
        raise SystemExit(f"active WebUI residue remains: {path.relative_to(ROOT)}")

# All live runtime headers must now follow module.prop instead of carrying historical branch labels.
for path in (ROOT / "common").iterdir():
    if not path.is_file() or path.name == "module_update_state.sh":
        continue
    try:
        value = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        continue
    for token in ("v13.", "v14.", "Beta", "Hotfix"):
        if token in value:
            raise SystemExit(f"historical runtime label remains in {path.relative_to(ROOT)}: {token}")

print("Font consistency source hygiene follow-up passed.")
