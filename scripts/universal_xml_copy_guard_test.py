#!/usr/bin/env python3
"""Real sealed XML validation and boot preflight; all mount/label I/O is mocked."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "common"), str(ROOT / "scripts")]
import fixed_static_xml_pipeline_test as fixture
import universal_font_deployment as deploy


class XmlCopyGuardTest(unittest.TestCase):
    def setUp(self):
        self.case = fixture.PipelineTest("test_shared_compile_payload_and_runtime")
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.root = self.case.root
        self.mod = self.root / "module"
        self.mod.mkdir()
        (self.mod / "common").symlink_to(ROOT / "common", target_is_directory=True)
        self.cfg = self.mod / "config"
        self.cfg.mkdir()
        self.payload = self.mod / ".luoshu-payload"
        shutil.copytree(self.case.payload, self.payload)
        self.d = copy.deepcopy(self.case.deployment)
        self.source = self.payload / "system/etc"
        self.stock = self.root / "visible/system/etc"
        self.stock.mkdir(parents=True, exist_ok=True)
        for logical, doc in self.case.route["documents"].items():
            if doc["operations"]:
                shutil.copyfile(doc["sourcePath"], self.stock / Path(logical).name)
        self.xml = next(self.source.iterdir()).name
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.command("getprop", "printf '%s\\n' " + repr(self.case.plan["device"]["buildKey"]))
        self.command("getenforce", "echo Enforcing")
        self.command("id", "echo 0")
        self.command("ls", "case \"$1\" in -Zd) echo \"u:object_r:system_file:s0 $2\" ;; *) exec /bin/ls \"$@\" ;; esac")
        self.command("mount-marker", "echo mounted >> " + repr(str(self.root / "mounts")))
        (self.cfg / "active_font.conf").write_text("mix\n")
        (self.cfg / "universal-font-runtime.conf").write_text(
            "state=active\npipeline=universal-font-deployment-v1\nfont=mix\n"
            "deploymentId=" + self.d["deploymentId"] + "\npayloadDigest=" + self.d["payloadDigest"] + "\n")
        self.env = dict(os.environ, MODDIR=str(self.mod), MODULE_DIR=str(self.mod), LUOSHU_PYTHON=sys.executable,
                        PATH=str(self.bin) + ":" + os.environ["PATH"],
                        LUOSHU_SELF_MOUNT_VISIBLE_ROOT=str(self.root / "visible"),
                        LUOSHU_SELF_MOUNT_STATE_ROOT=str(self.root / "self-state"),
                        LUOSHU_UNIVERSAL_MOUNT_STATE_ROOT=str(self.root / "mount-state"),
                        LUOSHU_UNIVERSAL_TEST_MANAGER="Magisk",
                        LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND=str(self.bin / "mount-marker"))

    def command(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def proof(self, **kwargs):
        deploy.validate_system_xml_copy_scope(self.d, self.payload, self.stock, **kwargs)

    def hook(self):
        return subprocess.run(["sh", str(ROOT / "common/universal_mount_runtime.sh"), "hook", "post-fs-data"],
                              env=self.env, capture_output=True, text=True, timeout=20)

    def blocked(self):
        result = self.hook()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "mounts").exists(), "preflight reached the mount command")

    def reseal(self):
        self.d["payloadDigest"] = deploy._payload_digest(self.d["files"], self.d["dynamicMounts"])
        keys = ("fontPlanId", "routeId", "artifactManifestId", "payloadDigest", "files", "dynamicMounts", "backendProfiles", "verificationContracts")
        self.d["deploymentId"] = "sha256:" + deploy._canonical_hash({key: self.d[key] for key in keys})
        self.d["runtimeManifest"]["deploymentId"] = self.d["deploymentId"]
        (self.payload / ".luoshu-runtime/deployment/deployment.json").write_text(json.dumps(self.d))

    def test_real_valid_scope_and_repeated_preflight(self):
        before = {p.name: p.read_bytes() for p in self.stock.iterdir()}
        copied = self.root / "memory-copy"
        shutil.copytree(self.source, copied)
        self.proof(copy_root=copied)
        for _ in range(2):
            result = self.hook()
            self.assertEqual(result.returncode, 0, result.stderr + (self.mod / "logs/universal-mount.log").read_text())
        self.assertEqual({p.name: p.read_bytes() for p in self.stock.iterdir()}, before)
        self.assertEqual((self.root / "mounts").read_text().splitlines(), ["mounted", "mounted"])

    def test_payload_tamper_is_rejected_before_mount(self):
        (self.source / self.xml).write_text("changed")
        self.blocked()

    def test_wrong_stock_same_firmware_is_rejected_before_mount(self):
        (self.stock / self.xml).write_text("changed stock")
        self.blocked()

    def test_runtime_identity_mismatch_is_rejected_before_mount(self):
        path = self.cfg / "universal-font-runtime.conf"
        path.write_text(path.read_text().replace(self.d["deploymentId"], "sha256:wrong"))
        self.blocked()

    def test_permissive_unknown_disabled_and_nonroot_are_rejected(self):
        for mode in ("Permissive", "Disabled", "Unknown", ""):
            with self.subTest(mode=mode):
                self.command("getenforce", "echo " + repr(mode))
                self.blocked()
        self.command("getenforce", "echo Enforcing")
        self.command("id", "echo 2000")
        self.blocked()

    def test_unreadable_original_label_is_rejected_before_mount(self):
        self.command("ls", "exit 1")
        self.blocked()

    def test_copy_corruption_is_rejected(self):
        copied = self.root / "memory-copy"
        shutil.copytree(self.source, copied)
        (copied / self.xml).write_text("corrupt")
        with self.assertRaisesRegex(deploy.DeploymentError, "memory copy"):
            self.proof(copy_root=copied)

    def test_missing_or_linked_stock_is_rejected(self):
        path = self.stock / self.xml
        content = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(deploy.DeploymentError, "exact regular stock"):
            self.proof()
        other = self.root / "other.xml"
        other.write_bytes(content)
        path.symlink_to(other)
        with self.assertRaisesRegex(deploy.DeploymentError, "exact regular stock"):
            self.proof()

    def test_source_must_be_exact_active_tree(self):
        source = self.root / "other-source"
        shutil.copytree(self.source, source)
        with self.assertRaisesRegex(deploy.DeploymentError, "active payload tree"):
            self.proof(source_root=source)

    def test_copy_extra_directory_symlink_and_hidden_file_are_rejected(self):
        copied = self.root / "memory-copy"
        shutil.copytree(self.source, copied)
        extra = copied / ".extra"
        extra.write_text("extra")
        with self.assertRaises(deploy.DeploymentError):
            self.proof(copy_root=copied)
        extra.unlink()
        entry = copied / self.xml
        entry.unlink()
        entry.mkdir()
        with self.assertRaises(deploy.DeploymentError):
            self.proof(copy_root=copied)
        entry.rmdir()
        entry.symlink_to(self.source / self.xml)
        with self.assertRaises(deploy.DeploymentError):
            self.proof(copy_root=copied)

    def test_valid_deployment_without_fixed_seal_cannot_authorize_copy(self):
        self.d["verificationContracts"].pop("fixedStaticRoute")
        (self.payload / ".luoshu-runtime/deployment/fixed-static-route-plan.json").unlink()
        self.reseal()
        deploy.validate_payload_integrity(self.d, self.payload)
        with self.assertRaisesRegex(deploy.DeploymentError, "sealed fixed-static"):
            self.proof()

    def test_resealed_wrong_xml_metadata_is_rejected(self):
        next(item for item in self.d["files"] if item["kind"] == "xml")["sourceXml"] = "/vendor/etc/fonts.xml"
        self.reseal()
        with self.assertRaisesRegex(deploy.DeploymentError, "sealed route"):
            self.proof()

    def test_fixed_snapshot_tamper_is_rejected(self):
        path = self.payload / ".luoshu-runtime/deployment/fixed-static-route-plan.json"
        path.write_text(path.read_text() + " ")
        self.blocked()

    def owned_lower(self):
        state = Path(self.env["LUOSHU_SELF_MOUNT_STATE_ROOT"])
        lower = state / "lower/system-etc"
        lower.parent.mkdir(parents=True)
        shutil.copytree(self.stock, lower)
        memory = state / "memory-layers/system-etc"
        memory.parent.mkdir(parents=True)
        shutil.copytree(self.source, memory)
        (state / "overlay-intents").mkdir()
        (state / "boot-id").write_text("test-boot\n")
        (state / "mounts.list").write_text(str(lower) + "\n")
        (self.root / "mountinfo").write_text("40 1 0:1 / " + str(lower) + " ro - ext4 rom ro\n")
        return state, lower, memory

    def run_shell(self, body, extra_env=None):
        # Source all actual runtime functions through an intentionally wrong
        # hook, then replace only kernel-facing observation primitives.
        script = '''
set -- hook wrong-stage
. "$MODDIR/common/universal_mount_runtime.sh"
_luoshu_atomic_boot_id() { echo test-boot; }
_luoshu_visible_mount_id() { echo "${VISIBLE_ID:-42}"; }
_luoshu_owned_mount_matches() { [ "${OWNER_OK:-1}" = 1 ]; }
awk() {
    case "$*" in
      */proc/self/mountinfo) command awk -v p="$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-etc" '$5==p{ok=1}END{exit !ok}' "$TEST_ROOT/mountinfo" ;;
      *) command awk "$@" ;;
    esac
}
_ufmr_validate_payload || exit 1
''' + body
        env = dict(self.env, TEST_ROOT=str(self.root), **(extra_env or {}))
        return subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True, timeout=20)

    def test_same_boot_owned_lower_is_reused_and_foreign_owner_is_rejected(self):
        state, lower, memory = self.owned_lower()
        target = str(self.stock.resolve())
        (state / "overlay-intents/system-etc").write_text(f"{memory}|{lower}|{target}|41|42\n")
        shutil.copyfile(self.source / self.xml, self.stock / self.xml)
        result = self.run_shell('_ufmr_system_mount')
        self.assertEqual(result.returncode, 0, result.stderr)
        for override in ({"VISIBLE_ID": "43"}, {"OWNER_OK": "0"}):
            result = self.run_shell('_ufmr_system_mount', override)
            self.assertNotEqual(result.returncode, 0)
        (state / "boot-id").write_text("previous-boot\n")
        # A normal reboot has stock visible again. Old journal state must not
        # block preflight or be mistaken for permission to use an old lower.
        shutil.copyfile(lower / self.xml, self.stock / self.xml)
        result = self.run_shell('_ufmr_system_mount')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_scoped_callback_rechecks_stock_copy_and_original_labels(self):
        state, lower, memory = self.owned_lower()
        self.command("ls", '''
case "$1" in
  -Zd)
    label=u:object_r:system_file:s0
    if [ -e "$TEST_ROOT/changed-label" ]; then
      case "$2" in "$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/"*) label=u:object_r:wrong_file:s0 ;; esac
    fi
    echo "$label $2" ;;
  *) exec /bin/ls "$@" ;;
esac''')
        body = '''
LUOSHU_UNIVERSAL_TEST_SYSTEM_MOUNT_COMMAND=
luoshu_private_self_mount_ensure() {
    _lsme_mount_list="$LUOSHU_SELF_MOUNT_STATE_ROOT/mounts.list"
    case "${FAULT:-}" in
      copy) printf corrupt > "$LUOSHU_SELF_MOUNT_STATE_ROOT/memory-layers/system-etc/''' + self.xml + '''" ;;
      stock) printf changed > "$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-etc/''' + self.xml + '''" ;;
      label) touch "$TEST_ROOT/changed-label" ;;
      runtime) printf 'deploymentId=sha256:changed\npayloadDigest=sha256:changed\n' > "$RUNTIME_CONF" ;;
    esac
    _luoshu_universal_xml_copy_check "$PAYLOAD/system/etc" "$LUOSHU_SELF_MOUNT_STATE_ROOT/lower/system-etc" "$LUOSHU_SELF_MOUNT_STATE_ROOT/memory-layers/system-etc"
}
_ufmr_system_mount
'''
        result = self.run_shell(body)
        self.assertEqual(result.returncode, 0, result.stderr)
        for fault in ("copy", "stock", "label", "runtime"):
            with self.subTest(fault=fault):
                shutil.copyfile(self.source / self.xml, memory / self.xml)
                shutil.copyfile(self.stock / self.xml, lower / self.xml)
                (self.root / "changed-label").unlink(missing_ok=True)
                result = self.run_shell(body, {"FAULT": fault})
                self.assertNotEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
