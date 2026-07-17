#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
app = root / 'webroot/app.js'
text = app.read_text(encoding='utf-8')
text = text.replace("let version = 'v13.4 Beta2 Hotfix6';", "let version = 'v14.1';")
text = text.replace('// v13.4 Beta2 Hotfix6 — variable/static family weight control + ZIP package import', '// 洛书 v14.1 — 完整复合字体与安全切换')
app.write_text(text, encoding='utf-8')

notes = root / 'config/version_notes.conf'
notes.parent.mkdir(parents=True, exist_ok=True)
notes.write_text(
    'version=v14.1\n'
    'summary=完整复合字体正式版\n'
    'notes=中文字体保持完整，英文与数字只替换对应字形；不覆盖字体 XML；支持任务进度、缓存复用、失败回滚和 Mountify 同步。\n',
    encoding='utf-8',
)

third = root / 'licenses/THIRD_PARTY.txt'
third.parent.mkdir(parents=True, exist_ok=True)
third.write_text(
    'LuoShu v14.1 bundles an official CPython Android ARM64 runtime and FontTools.\n\n'
    'Bundled runtime changes are packaging-only: development headers, tests, IDLE,\n'
    'ensurepip and other tools not used by LuoShu were removed to reduce module size.\n'
    'The interpreter and shared libraries are otherwise unmodified.\n\n'
    'Licenses:\n'
    '- CPython: licenses/CPython-LICENSE.txt\n'
    '- FontTools: licenses/FontTools-LICENSE.txt\n',
    encoding='utf-8',
)
print('materialized part4')
