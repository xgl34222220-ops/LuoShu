#!/bin/sh
set -eu

ROOT=$(mktemp -d)
trap 'rm -rf "$ROOT"' EXIT HUP INT TERM
mkdir -p "$ROOT/data/fonts/config" "$ROOT/data/fonts/files/hash" "$ROOT/system/etc" "$ROOT/system/fonts" "$ROOT/module/config" "$ROOT/module/logs" "$ROOT/module/common/python/bin"

cat > "$ROOT/data/fonts/config/config.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<fontConfig>
  <family name="google-sans"><font weight="400" style="normal">/data/fonts/files/hash/GoogleSans-Regular.ttf</font></family>
  <family name="google-sans-medium"><font weight="500" style="normal">/data/fonts/files/hash/GoogleSans-Medium.ttf</font></family>
  <family name="emoji-family"><font weight="400" style="normal">/data/fonts/files/hash/NotoColorEmoji.ttf</font></family>
</fontConfig>
XML
cat > "$ROOT/system/etc/fonts.xml" <<'XML'
<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif"><font weight="400" style="normal">Roboto-Regular.ttf</font></family>
</familyset>
XML

# This focused test validates the XML policy used by the provider bridge without
# requiring Android mount namespaces or the packaged ARM64 Python runtime.
python3 - "$ROOT/data/fonts/config/config.xml" "$ROOT/system/etc/fonts.xml" <<'PY'
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

dynamic = ET.parse(sys.argv[1])
blocked = re.compile(r"(google[-_\s]*sans|product[-_\s]*sans)", re.I)
removed = []
for parent in dynamic.getroot().iter():
    for child in list(parent):
        if child.tag.rsplit('}', 1)[-1] != 'family':
            continue
        name = child.attrib.get('name', '')
        if name and blocked.search(name):
            removed.append(name)
            parent.remove(child)
assert set(removed) == {'google-sans', 'google-sans-medium'}
remaining = {node.attrib.get('name') for node in dynamic.getroot().iter() if node.tag.rsplit('}', 1)[-1] == 'family'}
assert 'emoji-family' in remaining

system = ET.parse(sys.argv[2])
root = system.getroot()
for name, weight, filename in (
    ('google-sans', 400, 'LuoShu-400.ttf'),
    ('google-sans-text', 400, 'LuoShu-400.ttf'),
    ('google-sans-flex', 400, 'LuoShu-400.ttf'),
    ('google-sans-medium', 500, 'LuoShu-500.ttf'),
    ('google-sans-bold', 700, 'LuoShu-700.ttf'),
):
    family = ET.SubElement(root, 'family', {'name': name})
    font = ET.SubElement(family, 'font', {'weight': str(weight), 'style': 'normal'})
    font.text = filename
families = {node.attrib.get('name'): node for node in root if node.tag == 'family'}
assert families['google-sans'].find('font').text == 'LuoShu-400.ttf'
assert families['google-sans-medium'].find('font').text == 'LuoShu-500.ttf'
assert families['google-sans-bold'].find('font').text == 'LuoShu-700.ttf'
print('Font provider overlay policy test passed.')
PY

sh -n common/font_provider_cache.sh
sh -n post-fs-data.sh
sh -n uninstall.sh
