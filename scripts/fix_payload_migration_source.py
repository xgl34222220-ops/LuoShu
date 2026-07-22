#!/usr/bin/env python3
from pathlib import Path

path = Path(__file__).with_name("payload_schema_migration.py")
text = path.read_text(encoding="utf-8")
start_token = "state = state.replace(\n    '        \"$_module/config/app_install_manual\""
end_token = "state = state.replace(\n    '''        cache/full-composite-v5"
start = text.index(start_token)
end = text.index(end_token, start)
replacement = '''state = state.replace(
    """        "$_module/config/app_install_manual" \\
        "$_module/.font_switch.lock"""",
    """        "$_module/config/app_install_manual" \\
        "$_module/config/font-payload-rebuild-pending.conf" \\
        "$_module/.font_switch.lock"""",
    1,
)
'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("payload migration quoting fixed")
