#!/usr/bin/env python3
"""Safe manual stock-font inventory wrapper for LuoShu private payload mode."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import font_inventory as inventory
import font_inventory_scan as scanner


_ACTIVE_OVERLAY_MODULE: Path | None = None
_INSTALL_SNAPSHOTS: list[Path] = []
_SNAPSHOT_NAMESPACE_READY = False


def _dynamic_manifest_partitions(module: Path | None) -> list[str]:
    if module is None:
        return []
    manifest = module / "config/device_font_partitions.conf"
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    found: list[str] = []
    for value in lines:
        name = value.strip()
        if not name or not name.replace("_", "").isalnum() or name[0].isdigit():
            continue
        if name not in found:
            found.append(name)
    return found


def _logical_font_roots(module: Path | None) -> list[tuple[str, Path]]:
    roots = list(inventory.LOGICAL_FONT_ROOTS)
    known = {partition for partition, _logical in roots}
    for partition in _dynamic_manifest_partitions(module):
        if partition in known:
            continue
        roots.append((partition, Path("/") / partition / "fonts"))
        known.add(partition)
    return roots


def _private_partition_overlaid(partition: str) -> bool:
    module = _ACTIVE_OVERLAY_MODULE
    if module is None:
        return False
    for payload in (module / ".luoshu-payload", module / ".luoshu-payload-next", module):
        root = payload / partition
        if not root.is_dir():
            continue
        try:
            for path in root.rglob("*"):
                if inventory._font_file_candidate(path):
                    return True
        except OSError:
            continue
    return False


def _partition_logical_candidates(partition: str, logical_partition: Path) -> list[Path]:
    found: list[Path] = []

    def add(path: Path) -> None:
        if path not in found:
            found.append(path)

    add(logical_partition)
    for name, logical, _argument, aliases in scanner.PRIMARY_FONT_SPECS:
        if name != partition:
            continue
        add(logical.parent)
        for alias in aliases:
            add(alias.parent)
    for name, logical, _argument in scanner.AUX_FONT_SPECS:
        if name == partition:
            add(logical.parent)
    try:
        dynamic = scanner._dynamic_partition_specs()
    except Exception:
        dynamic = []
    for name, logical, aliases, _etc_logical, _etc_aliases in dynamic:
        if name != partition:
            continue
        add(logical.parent)
        for alias in aliases:
            add(alias.parent)
    return found


def _partition_has_mount(path: Path) -> bool:
    root = str(path).rstrip("/")
    for target in _mount_targets():
        if target == root or target.startswith(root + "/"):
            return True
    return False


def _safe_partition_census_root(
    partition: str,
    logical_partition: Path,
    derived_actual: Path,
) -> Path | None:
    """Resolve a trustworthy whole-partition view for scanner revision 6.

    Standard font lower directories are intentionally *not* whole partitions.
    During an in-place LuoShu update, walking upward from
    /data/adb/luoshu/self-mount/lower/product-fonts would incorrectly census the
    lower-state directory instead of /product, hiding /product/vivo/fonts and
    every other nested OEM root. Prefer full mirrors, installer-stock namespaces
    or a non-recursive parent bind snapshot.
    """
    if _ACTIVE_OVERLAY_MODULE is None:
        return derived_actual if derived_actual.is_dir() else None

    candidates = _partition_logical_candidates(partition, logical_partition)

    # Magisk-style mirrors are the strongest whole-partition stock source.
    for logical in candidates:
        try:
            relative = logical.relative_to("/")
        except ValueError:
            continue
        for prefix in inventory.MIRROR_PREFIXES:
            mirror = prefix / relative
            if mirror.is_dir():
                return mirror

    # KernelSU/SukiSU installers may already see an isolated stock namespace.
    for logical in candidates:
        if logical.is_dir() and _installer_namespace_is_stock(logical):
            return logical

    # A non-recursive bind of the partition parent omits LuoShu's child mounts
    # (/product/fonts, /product/vivo/fonts, ...), exposing the underlying stock
    # filesystem without changing the live namespace.
    for logical in candidates:
        if not logical.is_dir():
            continue
        snapshot = _bind_parent_stock_snapshot(logical)
        if snapshot is not None:
            return snapshot

    # If LuoShu has no payload in this partition and there are no mounts at or
    # below it, the live partition is already a trustworthy stock view.
    if not _private_partition_overlaid(partition):
        for logical in candidates:
            if logical.is_dir() and not _partition_has_mount(logical):
                return logical

    return None


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
        for _partition, logical in _logical_font_roots(module):
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
    if root in targets and not _readonly_partition_mount(logical):
        return []
    return sorted(target for target in targets if target.startswith(root + "/"))


def _readonly_partition_mount(logical: Path) -> bool:
    """Only a block-backed read-only partition is safe to snapshot as a parent.

    A /product erofs mount itself is normal; a non-recursive bind still omits
    overlays mounted under /product/fonts. An overlay/tmpfs/file bind at the
    selected parent can instead contain replacement bytes and is rejected.
    """
    source = Path(os.environ.get("LUOSHU_MOUNTINFO", "/proc/self/mountinfo"))
    try:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False
    found = []
    for line in lines:
        fields = line.split()
        try:
            split = fields.index("-")
            if _unescape_mount_path(fields[4]) != str(logical).rstrip("/"):
                continue
            found.append(fields[split + 1] in {"erofs", "ext4", "squashfs", "f2fs"}
                         and fields[split + 2].startswith("/dev/block/")
                         and _unescape_mount_path(fields[3]) in {"/", "/" + logical.name}
                         and "ro" in fields[5].split(","))
        except (ValueError, IndexError):
            continue
    return bool(found) and all(found)


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


def _private_snapshot_namespace() -> bool:
    """Keep temporary stock bind mounts private even if the worker is killed."""
    global _SNAPSHOT_NAMESPACE_READY
    if _SNAPSHOT_NAMESPACE_READY:
        return True
    try:
        os.unshare(os.CLONE_NEWNS)
    except (AttributeError, OSError):
        return False
    # A new mount namespace can still share propagation with its parent. Detach
    # every inherited mount before making even the first temporary stock bind.
    if not _run_mount("--make-rprivate", "/"):
        return False
    _SNAPSHOT_NAMESPACE_READY = True
    return True


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
    if not _private_snapshot_namespace():
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


def _system_namespace_pids() -> list[str]:
    """Return a few long-lived Android processes that should see live font mounts."""
    wanted_exact = {"system_server", "zygote", "zygote64"}
    wanted_suffix = {"/com.android.systemui", ":com.android.systemui"}
    found: list[str] = ["1"]
    proc = Path("/proc")
    try:
        entries = list(proc.iterdir())
    except OSError:
        return found
    for entry in entries:
        if not entry.name.isdigit() or entry.name == str(os.getpid()):
            continue
        try:
            raw = (entry / "cmdline").read_bytes().split(b"\0", 1)[0]
            cmd = raw.decode("utf-8", errors="ignore")
        except OSError:
            continue
        base = Path(cmd).name
        if base in wanted_exact or cmd == "com.android.systemui" or any(cmd.endswith(s) for s in wanted_suffix):
            if entry.name not in found:
                found.append(entry.name)
        if len(found) >= 8:
            break
    return found


def _installer_namespace_is_stock(logical: Path) -> bool:
    """Prove the flash process sees stock while a system process sees LuoShu.

    KernelSU/SukiSU may run module installers in a private mount namespace.
    active_font.conf can still say mix even though this process already sees the
    lower stock tree. Compare actual font bytes against several long-lived Android
    namespaces (init, system_server, zygote, SystemUI) and trust the installer
    tree only when a system namespace matches LuoShu payload while the installer
    sees different bytes at the exact same logical path.
    """
    module = _ACTIVE_OVERLAY_MODULE
    if module is None or not logical.is_dir():
        return False
    self_ns = _mount_namespace_id("self")
    if not self_ns:
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
    target_pids = [
        pid for pid in _system_namespace_pids()
        if _mount_namespace_id(pid) and _mount_namespace_id(pid) != self_ns
    ]
    if not target_pids:
        return False

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
            if not installer_file.is_file():
                continue
            payload_sig = _quick_file_signature(payload_file)
            installer_sig = _quick_file_signature(installer_file)
            if payload_sig is None or installer_sig is None:
                continue

            # Seeing even one exact payload file in the installer namespace means
            # it is not a clean stock view. Fail closed.
            if installer_sig == payload_sig:
                return False

            for pid in target_pids:
                live_file = Path(f"/proc/{pid}/root") / relative_root / rel
                if not live_file.is_file():
                    continue
                live_sig = _quick_file_signature(live_file)
                if live_sig is None:
                    continue
                checked += 1
                if live_sig == payload_sig and installer_sig != payload_sig:
                    return True
                if checked >= 16:
                    break
            if checked >= 16:
                break
        if checked >= 16:
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
    previous_census_resolver = scanner.PARTITION_CENSUS_ROOT_RESOLVER
    scanner.PARTITION_CENSUS_ROOT_RESOLVER = _safe_partition_census_root
    try:
        return scanner.main()
    finally:
        scanner.PARTITION_CENSUS_ROOT_RESOLVER = previous_census_resolver
        _cleanup_install_snapshots()


if __name__ == "__main__":
    raise SystemExit(main())
