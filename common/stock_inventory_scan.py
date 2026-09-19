#!/usr/bin/env python3
"""Safe manual stock-font inventory wrapper for LuoShu private payload mode."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import font_inventory as inventory
import font_inventory_scan_v3 as scanner


_ACTIVE_OVERLAY_MODULE: Path | None = None
_INSTALL_SNAPSHOTS: list[Path] = []


def _private_root_overlaid(logical: Path) -> bool:
    module = _ACTIVE_OVERLAY_MODULE
    if module is None:
        return False
    relative = logical.relative_to("/")
    for payload in (module / ".luoshu-payload", module / ".luoshu-payload-next", module):
        root = payload / relative
        if not root.is_dir():
            continue
        try:
            if any(path.is_file() for path in root.iterdir()):
                return True
        except OSError:
            continue
    return False


def _private_overlay_risk(module: Path | None) -> bool:
    global _ACTIVE_OVERLAY_MODULE
    _ACTIVE_OVERLAY_MODULE = None
    # LuoShu's early boot hook sets this only immediately before self-mount, while
    # skip_mount/skip_mountify still leave the logical ROM roots stock-visible.
    if os.environ.get("LUOSHU_STOCK_VIEW_VERIFIED", "").strip() == "1":
        return False
    if not module or not module.is_dir():
        return False
    try:
        active = (module / "config/active_font.conf").read_text(encoding="utf-8").splitlines()[0].strip()
    except (OSError, IndexError):
        active = ""
    if not active or active == "default":
        return False
    _ACTIVE_OVERLAY_MODULE = module

    payload_roots = (
        module / ".luoshu-payload",
        module / ".luoshu-payload-next",
        module,
    )
    for payload in payload_roots:
        for _partition, logical in inventory.LOGICAL_FONT_ROOTS:
            font_dir = payload / logical.relative_to("/")
            if not font_dir.is_dir():
                continue
            try:
                if any(
                    path.is_file() and path.suffix.lower() in inventory.FONT_EXTENSIONS
                    for path in font_dir.iterdir()
                ):
                    return True
            except OSError:
                continue
    # An active non-default selection must still be treated as overlay risk even if
    # its private payload is temporarily hidden from this process namespace.
    return True


def _unescape_mount_path(value: str) -> str:
    return (value.replace(r"\040", " ").replace(r"\011", "\t")
                 .replace(r"\012", "\n").replace(r"\134", "\\"))


def _mount_targets() -> set[str]:
    source = Path(os.environ.get("LUOSHU_MOUNTINFO", "/proc/self/mountinfo"))
    try:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return set()
    targets: set[str] = set()
    for line in lines:
        fields = line.split()
        if len(fields) >= 5:
            targets.add(_unescape_mount_path(fields[4]))
    return targets


def _child_mount_targets(logical: Path) -> list[str]:
    root = str(logical).rstrip("/")
    targets = _mount_targets()
    # If the directory itself is a mountpoint, a plain bind snapshot would only
    # duplicate that overlay. The recovery below is intentionally for per-file
    # bind layouts where the parent remains the stock filesystem.
    if root in targets:
        return []
    return sorted(target for target in targets if target.startswith(root + "/"))


def _run_mount(*args: str) -> bool:
    mount = shutil.which("mount") or ("/system/bin/mount" if Path("/system/bin/mount").is_file() else "")
    if not mount:
        return False
    try:
        return subprocess.run([mount, *args], check=False, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=8).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _run_umount(path: Path) -> None:
    umount = shutil.which("umount") or ("/system/bin/umount" if Path("/system/bin/umount").is_file() else "")
    if not umount:
        return
    try:
        subprocess.run([umount, str(path)], check=False, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=8)
    except (OSError, subprocess.SubprocessError):
        pass


def _bind_parent_stock_snapshot(logical: Path) -> Path | None:
    """Recover stock bytes hidden only by per-file bind mounts.

    A non-recursive bind of the parent filesystem does not clone child mounts.
    Therefore, when LuoShu's old runtime replaced individual font files, binding
    /system/fonts to a temporary path exposes the underlying stock directory
    without touching the live font mounts. We only trust the snapshot when at
    least one known child mount resolves to a different inode in the snapshot.
    Directory-level overlay mounts are deliberately rejected above.
    """
    children = _child_mount_targets(logical)
    if not children or not logical.is_dir():
        return None

    parts = [part for part in logical.parts if part not in ("/", "")]
    key = "-".join(parts[-2:] or ["root"])
    base = Path(os.environ.get("LUOSHU_INSTALL_STOCK_SNAPSHOT_ROOT",
                               f"/data/adb/luoshu/install-stock-scan/{os.getpid()}"))
    snapshot = base / key
    try:
        snapshot.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None

    if not _run_mount("--bind", str(logical), str(snapshot)):
        shutil.rmtree(snapshot, ignore_errors=True)
        return None
    _run_mount("--make-private", str(snapshot))

    proven = False
    for child in children:
        try:
            relative = Path(child).relative_to(logical)
        except ValueError:
            continue
        live = logical / relative
        stock = snapshot / relative
        try:
            live_stat = live.stat()
            stock_stat = stock.stat()
        except OSError:
            continue
        if (live_stat.st_dev, live_stat.st_ino) != (stock_stat.st_dev, stock_stat.st_ino):
            proven = True
            break

    if not proven:
        _run_umount(snapshot)
        shutil.rmtree(snapshot, ignore_errors=True)
        return None

    _INSTALL_SNAPSHOTS.append(snapshot)
    return snapshot


def _cleanup_install_snapshots() -> None:
    seen: set[Path] = set()
    for snapshot in reversed(_INSTALL_SNAPSHOTS):
        if snapshot in seen:
            continue
        seen.add(snapshot)
        _run_umount(snapshot)
    if _INSTALL_SNAPSHOTS:
        shutil.rmtree(_INSTALL_SNAPSHOTS[0].parents[0], ignore_errors=True)
    _INSTALL_SNAPSHOTS.clear()


def _quick_file_signature(path: Path) -> tuple[int, bytes, bytes] | None:
    try:
        size = path.stat().st_size
        if size <= 0:
            return None
        with path.open("rb") as stream:
            head = stream.read(65536)
            tail = b""
            if size > 65536:
                stream.seek(max(0, size - 65536))
                tail = stream.read(65536)
        return (int(size), head, tail)
    except OSError:
        return None


def _mount_namespace_id(pid: str) -> str:
    try:
        return os.readlink(f"/proc/{pid}/ns/mnt")
    except OSError:
        return ""


def _installer_namespace_is_stock(logical: Path) -> bool:
    """Prove that this flash process sees stock while PID 1 sees LuoShu payload.

    KernelSU/SukiSU can run module installers in a private mount namespace. In
    that case active_font.conf still says mix, but the install process's
    /system/fonts is already the lower stock tree. Trust it only when:
      1) installer and PID 1 are in different mount namespaces;
      2) at least one known LuoShu payload file matches PID 1's visible file; and
      3) the installer-visible file at the same path differs from that payload.
    This turns namespace isolation itself into a verified stock source instead of
    unnecessarily deferring every ColorOS scan until reboot.
    """
    module = _ACTIVE_OVERLAY_MODULE
    if module is None or not logical.is_dir():
        return False
    self_ns = _mount_namespace_id("self")
    init_ns = _mount_namespace_id("1")
    if not self_ns or not init_ns or self_ns == init_ns:
        return False

    try:
        relative_root = logical.relative_to("/")
    except ValueError:
        return False

    payload_roots = (
        module / ".luoshu-payload" / relative_root,
        module / ".luoshu-payload-next" / relative_root,
        module / relative_root,
    )
    pid1_root = Path(os.environ.get("LUOSHU_PID1_ROOT", "/proc/1/root")) / relative_root

    checked = 0
    for payload_root in payload_roots:
        if not payload_root.is_dir():
            continue
        try:
            payload_files = sorted(
                (path for path in payload_root.rglob("*")
                 if path.is_file() and path.suffix.lower() in inventory.FONT_EXTENSIONS),
                key=lambda path: str(path).lower(),
            )
        except OSError:
            continue
        for payload_file in payload_files[:24]:
            try:
                rel = payload_file.relative_to(payload_root)
            except ValueError:
                continue
            installer_file = logical / rel
            init_file = pid1_root / rel
            if not installer_file.is_file() or not init_file.is_file():
                continue
            payload_sig = _quick_file_signature(payload_file)
            init_sig = _quick_file_signature(init_file)
            installer_sig = _quick_file_signature(installer_file)
            if payload_sig is None or init_sig is None or installer_sig is None:
                continue
            checked += 1
            if init_sig == payload_sig and installer_sig != payload_sig:
                return True
            # If the installer itself already sees the payload for a sampled path,
            # it is not a clean stock namespace; fail closed immediately.
            if installer_sig == payload_sig:
                return False
            if checked >= 8:
                break
        if checked >= 8:
            break
    return False


def _safe_pick_actual_root(logical: Path, explicit: Path | None, overlay_risk: bool) -> Path:
    if explicit is not None:
        return explicit
    if not overlay_risk:
        return logical
    # Overlay risk is per partition, not global. A custom system/fonts payload
    # does not make an untouched vendor/fonts tree unsafe to scan directly.
    if _ACTIVE_OVERLAY_MODULE is not None and not _private_root_overlaid(logical):
        return logical

    parts = logical.parts
    if len(parts) >= 3 and parts[0] == "/":
        state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
        lower = state_root / "lower" / f"{parts[1]}-{parts[2]}"
        if lower.is_dir():
            return lower

    for prefix in inventory.MIRROR_PREFIXES:
        candidate = prefix / logical.relative_to("/")
        if candidate.is_dir():
            return candidate

    # KernelSU/SukiSU installers may be isolated from the active system mount
    # namespace. If PID 1 still sees LuoShu's payload while this process sees
    # different bytes at the same font path, the installer-visible tree is a
    # verified stock view and can be scanned immediately.
    if _installer_namespace_is_stock(logical):
        return logical

    # Old ColorOS/OPlus LuoShu builds often used per-file bind mounts and did not
    # persist a lower directory. Recover the parent stock filesystem in-place by
    # taking a non-recursive bind snapshot; this leaves the live mounted font
    # untouched and makes install-time universal scanning possible.
    snapshot = _bind_parent_stock_snapshot(logical)
    if snapshot is not None:
        return snapshot

    # A ROM is not required to expose every optional OEM partition. Missing logical
    # roots are harmless; an existing root without a verifiable stock view is not.
    if not logical.exists():
        return logical
    raise inventory.InventoryError(f"字体覆盖仍在活动且没有可验证的原厂 lower/mirror/snapshot：{logical}")


def main() -> int:
    inventory._overlay_risk = _private_overlay_risk
    inventory._pick_actual_root = _safe_pick_actual_root
    try:
        return scanner.main()
    finally:
        _cleanup_install_snapshots()


if __name__ == "__main__":
    raise SystemExit(main())
