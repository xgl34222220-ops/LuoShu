#!/usr/bin/env python3
from pathlib import Path
import os
import re
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: rc3_deep_clean.py <target-repository>')
os.chdir(sys.argv[1])


def read(path):
    return Path(path).read_text(encoding='utf-8')


def write(path, text):
    Path(path).write_text(text, encoding='utf-8')


def replace_once(path, old, new):
    text = read(path)
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{path}: exact match count {count}: {old[:100]!r}')
    write(path, text.replace(old, new, 1))


def sub_once(path, pattern, replacement, flags=re.S):
    text = read(path)
    new, count = re.subn(pattern, replacement, text, count=1, flags=flags)
    if count != 1:
        raise SystemExit(f'{path}: regex match count {count}: {pattern[:120]!r}')
    write(path, new)


# Folder launcher now exposes only text-font and ZIP-import directories.
replace_once('webroot/app.js', "        const safeKind = kind === 'emoji' ? 'emoji' : (kind === 'import' ? 'import' : 'fonts');", "        const safeKind = kind === 'import' ? 'import' : 'fonts';")
replace_once('webroot/app.js', "        const title = safeKind === 'emoji' ? 'Emoji' : (safeKind === 'import' ? '字体包导入' : '文字字体');", "        const title = safeKind === 'import' ? '字体包导入' : '文字字体';")

# Remove dead compatibility comments and state selectors.
replace_once('webroot/v14.css', '/* 移除不再公开的 Emoji 与自救弹窗，避免多个底部弹层相互叠加。 */\n', '')
replace_once('webroot/v14.css', 'body.stability-open{overflow:auto!important}\n', '')
replace_once('webroot/v14.css', '/* 洛书 v14 · 精简设置、稳定弹层与字体组合 */', '/* 洛书 v14 · 精简设置与字体组合 */')

# Delete the complete obsolete Emoji style block and remove its selectors from fallbacks.
sub_once('webroot/style.css', r'''\n/\* v13\.3 Beta2 — Emoji 独立管理 / 重启工作流 \*/\n\.emoji-section\{.*?\n\.emoji-card\.invalid[^\n]*\n''', '\n')
replace_once('webroot/style.css', '.font-section,.emoji-section,.current-card,.engine-card{scroll-margin-top:74px}', '.font-section,.current-card,.engine-card{scroll-margin-top:74px}')
replace_once('webroot/style.css', '.header-actions,.font-list,.font-card,.engine-card,.current-glass,.emoji-section,.modal-content{background:var(--card)}', '.header-actions,.font-list,.font-card,.engine-card,.current-glass,.modal-content{background:var(--card)}')
replace_once('webroot/style.css', '.font-card.active,.emoji-card.active,.variable-weight-control,.static-family-control{background:var(--surface-soft);border-color:var(--primary)}', '.font-card.active,.variable-weight-control,.static-family-control{background:var(--surface-soft);border-color:var(--primary)}')

# Refine layer: retain normal cards/runtime responsiveness, remove the old rescue sheet styling.
replace_once('webroot/ui_refine.css', '.luoshu-refined .engine-card,.luoshu-refined .emoji-section,.luoshu-refined .font-section,.luoshu-refined .quick-actions', '.luoshu-refined .engine-card,.luoshu-refined .font-section,.luoshu-refined .quick-actions')
ui = read('webroot/ui_refine.css')
lines = ui.splitlines()
clean = []
for line in lines:
    if line.startswith('body>#stabilityRescueButton') or line.startswith('.stability-modal') or line.startswith('[data-theme="dark"] .runtime-value,'):
        continue
    if line.startswith('@media(max-width:520px)'):
        line = line.replace('.stability-actions{grid-template-columns:1fr!important}.stability-actions button{min-height:70px!important}.stability-health-grid,.stability-info-grid{grid-template-columns:1fr!important}', '')
    clean.append(line)
ui = '\n'.join(clean) + '\n'
if re.search(r'emoji|stability', ui, flags=re.I):
    raise SystemExit('ui_refine.css still contains obsolete selectors')
write('webroot/ui_refine.css', ui)

# Analyzer keeps color-table detection as a safety signal, but no longer scores or reports Emoji coverage.
replace_once('webroot/font_analyzer.js', "    emoji: [0x1F600,0x1F602,0x1F60D,0x1F618,0x1F622,0x1F44D,0x1F44F,0x1F64F,0x1F389,0x1F525,0x1F680,0x1F4A1,0x1F4F1,0x1F496,0x1F31F,0x1F308,0x1F431,0x1F436,0x1F34E,0x1F37A],\n", '')
replace_once('webroot/font_analyzer.js', '    result.hasColorEmoji = Object.values(result.colorTables).some(Boolean);\n', '    result.hasColorTables = Object.values(result.colorTables).some(Boolean);\n')
replace_once('webroot/font_analyzer.js', "        `Emoji 字形：${c.emoji.percent}%${result.hasColorEmoji ? '（检测到彩色表）' : ''}`,\n", '')

# Strong postcondition for all WebUI sources.
for path in Path('webroot').rglob('*'):
    if not path.is_file() or path.suffix.lower() not in {'.js', '.css', '.html'}:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    if re.search(r'emoji|stability', text, flags=re.I):
        raise SystemExit(f'legacy WebUI token remains: {path}')
