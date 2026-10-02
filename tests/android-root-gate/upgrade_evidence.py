"""Synthetic upgrade preservation proof. Never writes Android Settings."""
import hashlib
import re
import shlex
import time

MODULE = '/data/adb/modules/LuoShu'
FONTS = '/sdcard/LuoShu/fonts'


def hashes(root, command):
    output = root(command)
    return {line.split(None, 1)[1]: line.split()[0]
            for line in output.splitlines() if re.match(r'^[0-9a-f]{64}  ', line)}


def snapshot(root):
    values = hashes(root, 'find ' + FONTS + r' -maxdepth 1 -type f \( -iname "*.ttf" -o -iname "*.otf" -o -iname "*.ttc" \) -exec sha256sum {} \;')
    for name in ('active_font.conf', 'font_mix.conf', 'axes_mix.conf', 'gate_upgrade_preserve.conf'):
        path = MODULE + '/config/' + name
        values.update(hashes(root, 'if [ -f ' + shlex.quote(path) + ' ]; then sha256sum ' + shlex.quote(path) + '; fi'))
    values.update(hashes(root, 'if [ -d ' + MODULE + '/config/recovery ]; then find ' + MODULE + r'/config/recovery -type f -exec sha256sum {} \; ; fi'))
    return values


def setting(root):
    current = root('settings --user current get secure font_weight_adjustment', required=False).strip()
    if not re.fullmatch(r'-?\d+', current):
        current = root('settings get secure font_weight_adjustment', required=False).strip()
    return current


def prepare(root):
    before = snapshot(root)
    sentinel = MODULE + '/config/gate_upgrade_preserve.conf'
    recovery = MODULE + '/config/recovery/gate-upgrade-preserve/keep.txt'
    root('test ! -e ' + sentinel + ' && test ! -e ' + recovery)
    root('mkdir -p ' + MODULE + '/config/recovery/gate-upgrade-preserve')
    for path in (sentinel, recovery):
        root('printf "%s\\n" ' + shlex.quote('Original synthetic upgrade-preservation sentinel; no user data') + ' > ' + shlex.quote(path))
    report = {'result': 'PENDING', 'existing_recovery_files': {p:h for p,h in before.items() if '/config/recovery/' in p},
              'synthetic_sentinels': [sentinel, recovery], 'expected_preserved': snapshot(root),
              'restore_api': 'NOT_RUN; preservation only', 'setting_before': setting(root),
              'settings_writes_by_harness': False, 'owned_current_restore_branch': 'HOST_ONLY; not exercised on Android'}
    value = report['setting_before']
    paths = [MODULE + '/config/font_weight.conf', MODULE + '/config/font_weight_original.conf',
             MODULE + '/config/recovery/retired-global-weight/font_weight.conf',
             MODULE + '/config/recovery/retired-global-weight/font_weight_original.conf']
    exists = root('for p in ' + shlex.join(paths) + '; do [ ! -e "$p" ] || echo "$p"; done')
    if re.fullmatch(r'-?\d+', value) and -1000 <= int(value) <= 1000 and not exists:
        original = int(value)
        saved = original + 1 if original < 1000 else original - 1
        report['weight_fixture'] = {'saved': saved, 'recorded_original': original, 'expected_archive_hashes': {}}
        for name, number in [('font_weight.conf', saved), ('font_weight_original.conf', original)]:
            content = f'adjustment={number}\n'
            root('printf %s ' + shlex.quote(content) + ' > ' + MODULE + '/config/' + name)
            report['weight_fixture']['expected_archive_hashes'][MODULE + '/config/recovery/retired-global-weight/' + name] = hashlib.sha256(content.encode()).hexdigest()
    else:
        report['weight_fixture'] = {'result': 'NOT_RUN', 'reason': 'No valid recorded system value or existing weight evidence must not be overwritten'}
    return report


def verify(root, report):
    actual = snapshot(root)
    missing = {p:expected for p,expected in report['expected_preserved'].items() if actual.get(p) != expected}
    if missing:
        report['mismatches'] = missing
        raise RuntimeError('Upgrade changed protected synthetic fonts/config/recovery bytes')
    report['preserved_hashes'] = {p:actual[p] for p in report['expected_preserved']}
    report['setting_after'] = setting(root)
    if report['setting_after'] != report['setting_before']:
        raise RuntimeError('Upgrade changed an unowned system font-weight value')
    expected = report['weight_fixture'].get('expected_archive_hashes')
    if expected:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            archived = hashes(root, 'if [ -d ' + MODULE + '/config/recovery/retired-global-weight ]; then find ' + MODULE + r'/config/recovery/retired-global-weight -type f -exec sha256sum {} \; ; fi')
            active = root('for p in ' + MODULE + '/config/font_weight.conf ' + MODULE + '/config/font_weight_original.conf; do [ ! -e "$p" ] || echo "$p"; done')
            if all(archived.get(p) == value for p,value in expected.items()) and not active:
                report['weight_fixture']['result'] = 'PASS_UNOWNED_SETTING_PRESERVED_AND_OLD_CONFIG_ARCHIVED'
                break
            time.sleep(1)
        else:
            raise RuntimeError('Retired weight fixture remains active or archive bytes differ')
    report['setting_after_final'] = setting(root)
    if report['setting_after_final'] != report['setting_before']:
        raise RuntimeError('Late boot changed an unowned system font-weight value')
    report['result'] = 'PASS'
    return report
