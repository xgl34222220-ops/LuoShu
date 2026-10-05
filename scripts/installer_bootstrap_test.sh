#!/bin/sh
# Host-side installer bootstrap regression. Optional argument: extracted module tree.
# This runs the actual wrapper and runtime-path migrator with every packaged file
# initially 0644. A shell shim at the bundled Python pathname executes host Python;
# it does NOT validate the Android ELF/loader/stdlib or the real delegated core.
set -eu
ROOT=$(CDPATH= cd -- "${1:-$(dirname -- "$0")/..}" && pwd)
[ "$#" -le 1 ] || { printf 'Usage: %s [module-tree]\n' "$0" >&2; exit 2; }
python3 - "$ROOT" <<'PY'
from pathlib import Path
import os
import shutil
import stat
import subprocess
import sys
import tempfile

root = Path(sys.argv[1]).resolve()
sources = ("customize.sh", "common/runtime_paths.sh", "common/runtime_paths_lock.py")
for name in sources:
    assert (root / name).is_file(), f"missing test input: {name}"

# The shim is intentionally installed as data (0644), like a normalized ZIP.
# It checks the real bundled-runtime selection before clearing Android-specific
# search paths for the host interpreter. Never set LUOSHU_RUNTIME_PATHS_PYTHON.
python_shim = r'''#!/bin/sh
[ "${LUOSHU_RUNTIME_PATHS_PYTHON+x}" != x ] || exit 90
[ "$PYTHONHOME" = "$MODPATH/common/python" ] || exit 91
[ "$PYTHONPATH" = "$PYTHONHOME/lib/python3.14:$PYTHONHOME/lib/python3.14/site-packages" ] || exit 92
case "$LD_LIBRARY_PATH" in "$PYTHONHOME/lib:$PYTHONHOME/lib/python3.14/lib-dynload"*) ;; *) exit 93 ;; esac
[ ! -e "$MODPATH/.bootstrap-core-ran" ] || exit 94
printf 'python\n' >> "$MODPATH/.bootstrap-events"
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH
exec "$LUOSHU_TEST_HOST_PYTHON" "$@"
'''

# Keep this core a boundary sentinel: none of the device/font/Root-manager code
# is executed. It must only run after the real runtime migration has succeeded.
# Its deliberately late chmod models the old core's permission setup, which
# cannot rescue a wrapper that attempted migration before preparing Python.
core = r'''#!/bin/sh
[ "${LUOSHU_RUNTIME_PATHS_PYTHON+x}" != x ] || return 81
[ -x "$MODPATH/common/python/bin/luoshu-python" ] || return 82
[ "$(readlink "$MODPATH/config")" = '.luoshu-state/config' ] || return 83
[ "$(cat "$MODPATH/.luoshu-state/paths-v1.conf")" = 'schema=luoshu-runtime-paths-v1' ] || return 84
[ "$(head -n1 "$MODPATH/.bootstrap-events")" = python ] || return 85
printf 'core\n' >> "$MODPATH/.bootstrap-events"
printf 'reached\n' > "$MODPATH/.bootstrap-core-ran"
chmod 0755 "$MODPATH/common/python/bin/luoshu-python"
return 0
'''
private_helper = r'''#!/bin/sh
luoshu_private_unmount_module_view() { return 0; }
luoshu_private_install_migrate() {
    [ -f "$1/.bootstrap-core-ran" ] || return 1
    printf 'private\n' >> "$1/.bootstrap-events"
}
'''


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(cases, name, update=False):
    module = cases / (name + " module with spaces")
    old = cases / (name + " old module")
    module.mkdir()
    old.mkdir()
    for relative in sources:
        target = module / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / relative, target)
    write(module / ".luoshu-runtime/compat/v227/customize.sh", core)
    write(module / "common/private_payload.sh", private_helper)
    write(module / "common/python/bin/luoshu-python", python_shim)
    write(module / "common/python/bin/unrelated-tool", "must remain non-executable\n")
    write(module / "common/python/lib/python3.14/site-packages/fixture.py", "# data\n")
    write(module / "config/active_font.conf", "用户选择\n" if update else "default\n")
    write(module / "config/nested/preference.conf", "preserve nested choice\n")
    write(module / "config/.hidden-preference", "preserve hidden choice\n")
    write(module / "system/fonts/fixture.ttf", "untouched payload bytes\n")
    if update:
        write(old / "config/active_font.conf", "旧版用户字体\n")
        write(old / "config/.hidden-preference", "old hidden preference\n")
        write(old / "system/fonts/fixture.ttf", "old active payload\n")
    # Do not rely on git executable bits or the test host's umask.
    for path in module.rglob("*"):
        if path.is_file():
            path.chmod(0o644)
    return module, old


def invoke(module, old):
    env = dict(os.environ)
    for key in tuple(env):
        if key.startswith("LUOSHU_") or key in ("CONFIG_DIR", "LOG_DIR", "TMPDIR", "MODDIR", "MODULE_DIR"):
            env.pop(key)
    env.update(MODPATH=str(module), LUOSHU_OLD_MOD=str(old),
               LUOSHU_TEST_HOST_PYTHON=sys.executable)
    return subprocess.run(["sh", "-c", '. "$1"', "installer-bootstrap-test", str(module / "customize.sh")],
                          env=env, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=15)


def snapshot(tree):
    return {str(p.relative_to(tree)): (p.read_bytes(), stat.S_IMODE(p.stat().st_mode))
            for p in tree.rglob("*") if p.is_file()}


def rejected(module, old, label):
    config_before = snapshot(module / "config")
    old_before = snapshot(old)
    result = invoke(module, old)
    assert result.returncode != 0, f"{label}: installer unexpectedly succeeded"
    assert "python" in result.stdout.lower(), f"{label}: no runtime-specific diagnostic: {result.stdout}"
    assert not (module / ".bootstrap-core-ran").exists(), f"{label}: delegated core ran"
    assert not (module / ".bootstrap-events").exists(), f"{label}: unsafe Python ran"
    assert not (module / ".luoshu-state").exists(), f"{label}: state migration started"
    assert snapshot(module / "config") == config_before, f"{label}: preferences changed"
    assert snapshot(old) == old_before, f"{label}: old module changed"
    print(f"PASS {label}: stopped before migration/core with runtime diagnostic")


with tempfile.TemporaryDirectory(prefix="luoshu-installer-bootstrap-") as temporary:
    cases = Path(temporary)
    for name, update in (("fresh", False), ("update", True)):
        module, old = fixture(cases, name, update)
        preferences = snapshot(module / "config")
        old_before = snapshot(old)
        binary = module / "common/python/bin/luoshu-python"
        assert stat.S_IMODE(binary.stat().st_mode) == 0o644
        result = invoke(module, old)
        assert result.returncode == 0, f"{name}: installer failed before delegated core: {result.stdout}"
        assert (module / ".bootstrap-events").read_text().splitlines() == ["python", "core", "private"], name
        assert stat.S_IMODE(binary.stat().st_mode) == 0o755, f"{name}: Python mode"
        assert snapshot(module / "config") == preferences, f"{name}: preferences not preserved"
        assert snapshot(old) == old_before, f"{name}: old module changed during bootstrap"
        for relative in ("common/python/bin/unrelated-tool", "common/python/lib/python3.14/site-packages/fixture.py", "system/fonts/fixture.ttf"):
            assert stat.S_IMODE((module / relative).stat().st_mode) == 0o644, f"{name}: overbroad chmod: {relative}"
        for relative in ("config", "logs", "cache", "backup", "reports"):
            assert os.readlink(module / relative) == ".luoshu-state/" + relative, f"{name}: {relative} link"
        print(f"PASS {name}: 0644 bundled path -> Python -> runtime migration -> delegated core; preferences preserved")

    module, old = fixture(cases, "missing-python", True)
    (module / "common/python/bin/luoshu-python").unlink()
    rejected(module, old, "missing bundled Python")

    # Every linked path component can redirect chmod or execution outside the
    # module. All targets remain inside this test's disposable temporary tree.
    for relative in ("common/python/bin/luoshu-python", "common/python/bin", "common/python", "common"):
        name = "symlink-" + relative.replace("/", "-")
        module, old = fixture(cases, name, True)
        linked = module / relative
        outside = cases / (name + " outside target")
        linked.rename(outside)
        linked.symlink_to(outside, target_is_directory=outside.is_dir())
        before = snapshot(outside) if outside.is_dir() else (outside.read_bytes(), stat.S_IMODE(outside.stat().st_mode))
        rejected(module, old, name)
        after = snapshot(outside) if outside.is_dir() else (outside.read_bytes(), stat.S_IMODE(outside.stat().st_mode))
        assert after == before, f"{name}: followed symlink to chmod/change outside target"

print("Installer bootstrap regression passed (host shim; Android runtime/device validation remains separate).")
PY
