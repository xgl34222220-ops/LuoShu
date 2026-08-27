#!/usr/bin/env python3
from pathlib import Path
import re


def read(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    Path(path).write_text(text, encoding="utf-8")


def must_replace(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"missing expected block: {path}")
    write(path, text.replace(old, new, 1))


# HyperOS: remove the failed global raw-metric bypass. Per-slot output owns metrics.
must_replace(
    "common/rom_adapters.sh",
    '''    # HyperOS has several independent physical font slots with different line-box contracts.\n    # Applying one main-slot hhea/OS2 contract to all of them moves text vertically in compact\n    # labels and EditText controls. Preserve the selected font/composite metrics on HyperOS;\n    # the ROM-specific mapper still selects only real UI slots and keeps protected scripts stock.\n    if [ "${IS_HYPEROS:-false}" = true ] && type _hyperos_compact_normalize >/dev/null 2>&1; then\n        if _hyperos_compact_normalize "$src" "$anchor" && [ -s "$anchor" ]; then\n            printf '%s\\n' "$anchor"\n            return 0\n        fi\n        rm -f "$anchor" 2>/dev/null || true\n    fi\n\n''',
    "",
)

# Inventory target path mapping: every supported physical font partition.
path = "common/rom_adapters.sh"
text = read(path)
pattern = re.compile(r"_device_font_inventory_target\(\) \{.*?\n\}\n\n_device_font_inventory_role\(\)", re.S)
replacement = '''_device_font_inventory_target() {
    _dfit_path="$1"
    _dfit_module="$(_device_font_inventory_module)"
    case "$_dfit_path" in
        /system/fonts/*) printf '%s/system/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/system/fonts/}" ;;
        /system_ext/fonts/*) printf '%s/system_ext/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/system_ext/fonts/}" ;;
        /product/fonts/*) printf '%s/product/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/product/fonts/}" ;;
        /vendor/fonts/*) printf '%s/vendor/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/vendor/fonts/}" ;;
        /odm/fonts/*) printf '%s/odm/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/odm/fonts/}" ;;
        /oem/fonts/*) printf '%s/oem/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/oem/fonts/}" ;;
        /my_product/fonts/*) printf '%s/my_product/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_product/fonts/}" ;;
        /my_engineering/fonts/*) printf '%s/my_engineering/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_engineering/fonts/}" ;;
        /my_company/fonts/*) printf '%s/my_company/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_company/fonts/}" ;;
        /my_preload/fonts/*) printf '%s/my_preload/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_preload/fonts/}" ;;
        /my_region/fonts/*) printf '%s/my_region/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_region/fonts/}" ;;
        /my_stock/fonts/*) printf '%s/my_stock/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/my_stock/fonts/}" ;;
        /oplus_product/fonts/*) printf '%s/oplus_product/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/oplus_product/fonts/}" ;;
        /oplus_engineering/fonts/*) printf '%s/oplus_engineering/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/oplus_engineering/fonts/}" ;;
        /oplus_version/fonts/*) printf '%s/oplus_version/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/oplus_version/fonts/}" ;;
        /oplus_region/fonts/*) printf '%s/oplus_region/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/oplus_region/fonts/}" ;;
        /mi_ext/fonts/*) printf '%s/mi_ext/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/mi_ext/fonts/}" ;;
        /cust/fonts/*) printf '%s/cust/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/cust/fonts/}" ;;
        /hw_product/fonts/*) printf '%s/hw_product/fonts/%s\\n' "$_dfit_module" "${_dfit_path#/hw_product/fonts/}" ;;
        *) return 1 ;;
    esac
}

_device_font_inventory_role()'''
text, n = pattern.subn(replacement, text, count=1)
if n != 1:
    raise SystemExit("inventory target mapper not found")

# ColorOS: inventory may discover OEM partitions, but production mapping stays on safe roots.
text = text.replace("    _dfii_count=0\n    _dfii_bad=0\n", "    _dfii_count=0\n    _dfii_bad=0\n    _dfii_skipped=0\n", 1)
needle = '''        [ -n "$_dfii_logical" ] && [ -n "$_dfii_name" ] || continue
        _dfii_target=$(_device_font_inventory_target "$_dfii_logical") || continue
'''
repl = '''        [ -n "$_dfii_logical" ] && [ -n "$_dfii_name" ] || continue
        if [ "${IS_COLOROS:-false}" = true ]; then
            case "$_dfii_logical" in
                /system/fonts/*|/system_ext/fonts/*|/product/fonts/*) ;;
                *) _dfii_skipped=$((_dfii_skipped + 1)); continue ;;
            esac
        fi
        _dfii_target=$(_device_font_inventory_target "$_dfii_logical") || {
            _dfii_skipped=$((_dfii_skipped + 1))
            continue
        }
'''
if needle not in text:
    raise SystemExit("inventory loop marker not found")
text = text.replace(needle, repl, 1)
needle = '''    LUOSHU_INVENTORY_TARGETS_MAPPED=1
    export LUOSHU_INVENTORY_TARGETS_MAPPED
    _log_step "  已按设备原厂清单覆盖 $_dfii_count 个真实字体槽位"
'''
repl = '''    LUOSHU_INVENTORY_TARGETS_MAPPED=1
    LUOSHU_SAFE_PHYSICAL_FALLBACK=1
    export LUOSHU_INVENTORY_TARGETS_MAPPED LUOSHU_SAFE_PHYSICAL_FALLBACK
    _log_step "  已按设备原厂清单覆盖 $_dfii_count 个真实字体槽位"
    [ "$_dfii_skipped" -eq 0 ] || _log_step "  已按 ROM 安全策略跳过 $_dfii_skipped 个非安全/未知字体槽位"
'''
if needle not in text:
    raise SystemExit("inventory success marker not found")
write(path, text.replace(needle, repl, 1))

# HyperOS: remove blind whole-partition secondary mirroring.
path = "common/font_mix.sh"
text = read(path)
text, n = re.subn(
    r'''    for _pair in \\\n        "vendor\|\$\{LUOSHU_VENDOR_FONTS_ROOT:-/vendor/fonts\}" \\\n        "odm\|\$\{LUOSHU_ODM_FONTS_ROOT:-/odm/fonts\}" \\\n        "oem\|\$\{LUOSHU_OEM_FONTS_ROOT:-/oem/fonts\}" \\\n        "my_product\|\$\{LUOSHU_MY_PRODUCT_FONTS_ROOT:-/my_product/fonts\}" \\\n        "hw_product\|\$\{LUOSHU_HW_PRODUCT_FONTS_ROOT:-/hw_product/fonts\}" \\\n        "cust\|\$\{LUOSHU_CUST_FONTS_ROOT:-/cust/fonts\}"; do\n        _part=\$\{_pair%%\|\*\}\n        _root=\$\{_pair#\*\|\}\n        \[ -d "\$_root" \] \|\| continue\n        sync_secondary_partition "\$_part" "\$_root" \|\| return 1\n    done\n''',
    "",
    text,
    count=1,
)
if n != 1:
    raise SystemExit("HyperOS blanket secondary sync not found")
write(path, text)

# ColorOS proven-safe allowlist: system/system_ext/product only.
path = "common/coloros_global.sh"
text = read(path)
text = re.sub(
    r'''(    printf '%s\|%s/product/fonts\\n'[^\n]+\n)(?:    printf '%s\|%s/(?:vendor|odm|oem|my_product|oplus_product|oplus_engineering|oplus_version|oplus_region)/fonts\\n'[^\n]+\n)+''',
    r"\1",
    text,
    count=1,
)
write(path, text)

# Foreground physical fallback: ColorOS must never fan out into dangerous partitions.
path = "common/device_font_payload_policy.sh"
text = read(path)
pattern = re.compile(r"_device_font_fast_alias_roots\(\) \{.*?\n\}\n\n_device_font_fast_map\(\)", re.S)
replacement = '''_device_font_fast_alias_roots() {
    _dffar_anchor="$1"
    _dffar_file="$2"
    _dffar_module="$(_device_font_policy_module)"
    _dffar_count=0
    if [ "${IS_COLOROS:-false}" = true ]; then
        _dffar_roots="/system/fonts|$_dffar_module/system/fonts
/system_ext/fonts|$_dffar_module/system_ext/fonts
/product/fonts|$_dffar_module/product/fonts"
    else
        _dffar_roots="/system/fonts|$_dffar_module/system/fonts
/system_ext/fonts|$_dffar_module/system_ext/fonts
/product/fonts|$_dffar_module/product/fonts
/mi_ext/fonts|$_dffar_module/mi_ext/fonts
/my_product/fonts|$_dffar_module/my_product/fonts
/vendor/fonts|$_dffar_module/vendor/fonts
/odm/fonts|$_dffar_module/odm/fonts
/oem/fonts|$_dffar_module/oem/fonts
/cust/fonts|$_dffar_module/cust/fonts
/hw_product/fonts|$_dffar_module/hw_product/fonts"
    fi
    while IFS='|' read -r _dffar_real _dffar_overlay; do
        [ -e "$_dffar_real/$_dffar_file" ] || continue
        mkdir -p "$_dffar_overlay" 2>/dev/null || continue
        rm -f "$_dffar_overlay/$_dffar_file" 2>/dev/null || true
        if ln "$_dffar_anchor" "$_dffar_overlay/$_dffar_file" 2>/dev/null || \
           cp -f "$_dffar_anchor" "$_dffar_overlay/$_dffar_file" 2>/dev/null; then
            chmod 0644 "$_dffar_overlay/$_dffar_file" 2>/dev/null || true
            _dffar_count=$((_dffar_count + 1))
        fi
    done <<EOF_DFFAR_ROOTS
$_dffar_roots
EOF_DFFAR_ROOTS
    printf '%s\\n' "$_dffar_count"
}

_device_font_fast_map()'''
text, n = pattern.subn(replacement, text, count=1)
if n != 1:
    raise SystemExit("fast alias root function not found")
needle = '''    _device_font_policy_log "前台快速映射完成：font=$_dffm_family aliases=$_dffm_total"
    return 0
'''
repl = '''    LUOSHU_SAFE_PHYSICAL_FALLBACK=1
    export LUOSHU_SAFE_PHYSICAL_FALLBACK
    _device_font_policy_log "前台快速映射完成：font=$_dffm_family aliases=$_dffm_total"
    return 0
'''
if needle not in text:
    raise SystemExit("fast-map completion marker not found")
text = text.replace(needle, repl, 1)
needle = '''    if [ -z "$_dfpp_template_key" ]; then
        _device_font_policy_log "设备对齐暂不可用：需要在系统默认字体状态重启一次建立原厂模板"
        LUOSHU_DEVICE_PAYLOAD_ERROR='缺少原厂字体模板；请先恢复系统默认字体并完整重启一次'
        export LUOSHU_DEVICE_PAYLOAD_ERROR
        return 2
    fi
'''
repl = '''    if [ -z "$_dfpp_template_key" ]; then
        if [ "${IS_COLOROS:-false}" = true ] && [ "${LUOSHU_SAFE_PHYSICAL_FALLBACK:-0}" = 1 ]; then
            _device_font_policy_log "ColorOS 原厂模板不可用；保留已验证的 system/system_ext/product 物理槽映射，不阻止切换"
            return 3
        fi
        _device_font_policy_log "设备对齐暂不可用：当前 ROM 没有可信原厂槽位模板"
        LUOSHU_DEVICE_PAYLOAD_ERROR='缺少可信原厂字体模板，未提交不确定的逐槽负载'
        export LUOSHU_DEVICE_PAYLOAD_ERROR
        return 2
    fi
'''
if needle not in text:
    raise SystemExit("template missing branch not found")
text = text.replace(needle, repl, 1)
needle = '''        1)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device-failed'
            return 1
            ;;
    esac
'''
repl = '''        1)
            LUOSHU_DEVICE_PAYLOAD_RESULT='device-failed'
            return 1
            ;;
        3)
            LUOSHU_DEVICE_PAYLOAD_RESULT='safe-physical-fallback'
            return 0
            ;;
    esac
'''
if needle not in text:
    raise SystemExit("payload result case not found")
write(path, text.replace(needle, repl, 1))

# Inventory: Xiaomi direct SystemUI/clock slots; use LuoShu self-mount lower before Magisk mirrors.
path = "common/font_inventory.py"
text = read(path)
needle = '    re.compile(r"^MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3)\\.(?:ttf|otf|ttc|otc)$", re.I),\n'
repl = '    re.compile(r"^MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3|Clock[A-Za-z0-9_.-]*)\\.(?:ttf|otf|ttc|otc)$", re.I),\n    re.compile(r"^(?:Mitype[A-Za-z0-9_.-]*|MiClock[A-Za-z0-9_.-]*|AndroidClock[A-Za-z0-9_.-]*|Clockopia)\\.(?:ttf|otf|ttc|otc)$", re.I),\n'
if needle not in text:
    raise SystemExit("MiSans heuristic marker not found")
text = text.replace(needle, repl, 1)
needle = '''    if overlay_risk:
        for prefix in MIRROR_PREFIXES:
            candidate = prefix / logical.relative_to("/")
            if candidate.is_dir():
                return candidate
        raise InventoryError(f"旧版字体覆盖仍在活动，无法安全读取原厂目录：{logical}")
'''
repl = '''    if overlay_risk:
        parts = logical.parts
        if len(parts) >= 3 and parts[0] == "/":
            state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
            lower = state_root / "lower" / f"{parts[1]}-{parts[2]}"
            if lower.is_dir():
                return lower
        for prefix in MIRROR_PREFIXES:
            candidate = prefix / logical.relative_to("/")
            if candidate.is_dir():
                return candidate
        raise InventoryError(f"字体覆盖仍在活动且没有可验证的原厂 lower/mirror：{logical}")
'''
if needle not in text:
    raise SystemExit("inventory overlay-risk marker not found")
write(path, text.replace(needle, repl, 1))

# Update install: rescan inventory with new policy; migration failure aborts instead of writing default.
path = ".luoshu-runtime/customize-v227.sh"
text = read(path)
needle = '            "$FONT_INVENTORY_PYTHON" "$FONT_INVENTORY_SCRIPT" --scan \\\n                --output "$FONT_INVENTORY_OUTPUT" \\\n'
repl = '            "$FONT_INVENTORY_PYTHON" "$FONT_INVENTORY_SCRIPT" --scan --force \\\n                --output "$FONT_INVENTORY_OUTPUT" \\\n'
if needle not in text:
    raise SystemExit("inventory scan invocation not found")
text = text.replace(needle, repl, 1)
needle = '''    printf 'default\\n' > "$MODPATH/config/active_font.conf"
fi

# 必须在新模块覆盖挂载系统字体之前读取原厂槽位。'''
repl = '''    _old_selected=$(head -n1 "$OLD_MOD/config/active_font.conf" 2>/dev/null | tr -d '\\r\\n')
    if [ -n "$_old_selected" ] && [ "$_old_selected" != default ]; then
        ui_print "✗ 无法安全迁移当前字体 $_old_selected；已中止本次更新，不会切回系统默认字体"
        exit 1
    fi
    printf 'default\\n' > "$MODPATH/config/active_font.conf"
fi

# 必须在新模块覆盖挂载系统字体之前读取原厂槽位。'''
if needle not in text:
    raise SystemExit("unsafe default migration fallback not found")
write(path, text.replace(needle, repl, 1))

# Final per-device payload: enrich old trusted XML templates with direct Xiaomi physical slots.
write("common/device_font_payload_build.py", '''#!/usr/bin/env python3
# Packaging contract marker: device-font-payload-v1
"""Per-device builder plus HyperOS physical slots that bypass fonts.xml."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import device_font_payload_build_base as _base
from device_font_payload_build_base import *  # noqa: F401,F403

_ORIGINAL_BUILD_SIGNATURE = _base.build_signature
_ORIGINAL_BUILD_PAYLOAD = _base.build_payload
_HYPEROS_DIRECT = re.compile(
    r"^(?:MiSans(?:VF(?:_Overlay)?|LatinVF|TCVF|L3|Clock[A-Za-z0-9_.-]*)|"
    r"Mitype[A-Za-z0-9_.-]*|MiClock[A-Za-z0-9_.-]*|AndroidClock[A-Za-z0-9_.-]*|Clockopia|"
    r"GoogleSans(?:Text|Flex)?[A-Za-z0-9_.-]*|Roboto(?:Flex|Static)?[A-Za-z0-9_.-]*|"
    r"SourceSansPro[A-Za-z0-9_.-]*|(?:100|200|300|350|400|500|600|700|800|900))"
    r"\\.(?:ttf|otf|ttc|otc)$", re.I
)
_DENY = ("italic", "oblique", "emoji", "symbol", "icon", "serif", "math", "music")
_ROOTS = ("system", "system_ext", "product", "mi_ext", "my_product", "vendor", "odm", "oem", "cust", "hw_product")


def build_signature(slot: dict[str, Any], source_profile: dict[str, Any], source_weight: int) -> str:
    return _ORIGINAL_BUILD_SIGNATURE(slot, source_profile, source_weight)


def _weight(name: str) -> int:
    lower = name.lower().replace("-", "").replace("_", "")
    hit = re.search(r"(?:^|[^0-9])(100|200|300|350|400|500|600|700|800|900)(?:[^0-9]|$)", name)
    if hit:
        return int(hit.group(1))
    for token, value in (("thin",100),("extralight",200),("light",300),("medium",500),("semibold",600),("bold",700),("extrabold",800),("black",900)):
        if token in lower:
            return value
    return 400


def _roles(name: str) -> list[str]:
    lower = name.lower()
    if any(token in lower for token in _DENY) or not _HYPEROS_DIRECT.fullmatch(name):
        return []
    if "clock" in lower:
        return ["clock", "global-ui"]
    if "mono" in lower:
        return ["mono", "global-ui"]
    if lower.startswith("mitype"):
        return ["display", "global-ui"]
    return ["global-ui"]


def _stock_file(module: Path, partition: str, name: str) -> Path | None:
    logical = Path("/") / partition / "fonts" / name
    state_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount"))
    lower = state_root / "lower" / f"{partition}-fonts" / name
    if lower.is_file():
        return lower
    for prefix in (Path("/debug_ramdisk/.magisk/mirror"), Path("/sbin/.magisk/mirror"), Path("/data/adb/magisk/mirror")):
        candidate = prefix / partition / "fonts" / name
        if candidate.is_file():
            return candidate
    if (module / partition / "fonts" / name).exists():
        return None
    return logical if logical.is_file() else None


def _enrich_hyperos(template: dict[str, Any]) -> dict[str, Any]:
    module = Path(__file__).resolve().parent.parent
    slots = template.get("slots") if isinstance(template.get("slots"), list) else []
    existing = {str(item.get("resolvedPath", "")) for item in slots if isinstance(item, dict)}
    candidates: list[tuple[str, str, Path, list[str]]] = []
    hyperos_marker = False
    for partition in _ROOTS:
        lower_root = Path(os.environ.get("LUOSHU_SELF_MOUNT_STATE_ROOT", "/data/adb/luoshu/self-mount")) / "lower" / f"{partition}-fonts"
        live_root = Path("/") / partition / "fonts"
        names: set[str] = set()
        for root in (lower_root, live_root):
            if not root.is_dir():
                continue
            try:
                names.update(item.name for item in root.iterdir() if item.is_file())
            except OSError:
                pass
        for name in sorted(names):
            roles = _roles(name)
            if not roles:
                continue
            if name.lower().startswith(("misans", "mitype", "miclock")):
                hyperos_marker = True
            logical = str(Path("/") / partition / "fonts" / name)
            if logical in existing:
                continue
            stock = _stock_file(module, partition, name)
            if stock is not None:
                candidates.append((partition, name, stock, roles))
    if not hyperos_marker:
        return template
    for partition, name, stock, roles in candidates:
        logical = str(Path("/") / partition / "fonts" / name)
        try:
            profile = _base.template_engine.inspect_font(stock, -1, hash_fonts=False)
        except Exception:
            continue
        slots.append({
            "family": f"physical-{name}", "familyNormalized": f"physical-{name}".lower(),
            "familyAttributes": {}, "sourceXml": "", "declared": name, "postScriptName": "",
            "weight": _weight(name), "style": "normal", "index": 0, "axes": "",
            "roles": roles, "replaceable": True, "resolvedPath": logical,
            "directPhysical": True, "font": profile,
        })
        existing.add(logical)
    template["slots"] = slots
    summary = template.setdefault("summary", {})
    summary["slots"] = len(slots)
    summary["replaceable"] = sum(1 for item in slots if item.get("replaceable"))
    summary["directPhysical"] = sum(1 for item in slots if item.get("directPhysical"))
    return template


def build_payload(template, source_dir, source_prefix, output_dir, manifest_path):
    return _ORIGINAL_BUILD_PAYLOAD(_enrich_hyperos(template), source_dir, source_prefix, output_dir, manifest_path)


_base.build_signature = build_signature
_base.build_payload = build_payload


def main() -> int:
    return _base.main()


if __name__ == "__main__":
    raise SystemExit(main())
''')

# Overlay renderer: direct physical slots must be installed under exact OEM filenames.
path = "common/device_font_payload_overlay.py"
text = read(path)
anchor = "def commit_directory(stage: Path, output: Path) -> None:\n"
direct_fn = '''def copy_direct_physical_slots(
    slots: list[dict[str, Any]], payload_root: Path, stage: Path, copied: dict[tuple[str, str], Path]
) -> int:
    count = 0
    for slot in slots:
        if slot.get("sourceXml") or not slot.get("generatedFile"):
            continue
        stock_path = str(slot.get("stockPath", ""))
        parts = Path(stock_path).parts
        if len(parts) < 4 or parts[0] != "/" or parts[2] != "fonts":
            raise OverlayError(f"物理字体槽路径无效：{stock_path}")
        partition, target_name = parts[1], parts[-1]
        generated_name = str(slot["generatedFile"])
        source = payload_root / "fonts" / generated_name
        if not source.is_file() or source.stat().st_size < 1024:
            raise OverlayError(f"物理槽生成字体不存在：{generated_name}")
        destination = stage / partition / "fonts" / target_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.link(source, destination)
        except OSError:
            shutil.copyfile(source, destination)
        os.chmod(destination, 0o644)
        copied[(partition, target_name)] = destination
        count += 1
    return count


'''
if direct_fn not in text:
    if anchor not in text:
        raise SystemExit("overlay commit marker not found")
    text = text.replace(anchor, direct_fn + anchor, 1)
needle = '''        by_xml: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for slot in slots:
            by_xml[str(slot.get("sourceXml", ""))].append(slot)

        system_trees:'''
repl = '''        by_xml: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for slot in slots:
            if slot.get("sourceXml"):
                by_xml[str(slot.get("sourceXml", ""))].append(slot)
        direct_physical = copy_direct_physical_slots(slots, payload_root, stage, copied)

        system_trees:'''
if needle not in text:
    raise SystemExit("overlay by_xml marker not found")
text = text.replace(needle, repl, 1)
needle = '''        if rewritten + dynamic_mapped != mapped:
            raise OverlayError(
                f"槽位映射不完整：mapped={mapped} rewritten={rewritten} dynamic={dynamic_mapped}"
            )
'''
repl = '''        if rewritten + dynamic_mapped + direct_physical != mapped:
            raise OverlayError(
                f"槽位映射不完整：mapped={mapped} rewritten={rewritten} dynamic={dynamic_mapped} physical={direct_physical}"
            )
'''
if needle not in text:
    raise SystemExit("overlay completeness marker not found")
text = text.replace(needle, repl, 1)
text = text.replace('                "dynamicSlots": dynamic_mapped,\n', '                "dynamicSlots": dynamic_mapped,\n                "directPhysicalSlots": direct_physical,\n', 1)
write(path, text)

# Device regression guard.
write("scripts/v4_rom_regression_test.sh", '''#!/bin/sh
set -eu
grep -q 'degraded:booting.*degraded:confirmed' common/device_font_load_verify.sh
! grep -A45 '^luoshu_payload_quarantine()' common/font_runtime_policy.sh | grep -q "printf 'default"
! grep -q '字体挂载连续三次不可见，已安全恢复系统默认字体' service_v4.sh
! grep -A25 '^_font_anchor()' common/rom_adapters.sh | grep -q '_hyperos_compact_normalize'
! grep -A35 '^sync_secondary_hyperos_dirs()' common/font_mix.sh | grep -q 'LUOSHU_VENDOR_FONTS_ROOT'
grep -A40 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '/mi_ext/fonts/'
grep -A40 '^_device_font_inventory_target()' common/rom_adapters.sh | grep -q '/hw_product/fonts/'
grep -q 'Mitype' common/font_inventory.py
grep -q 'MiClock' common/font_inventory.py
grep -q 'directPhysicalSlots' common/device_font_payload_overlay.py
grep -q 'physical-{name}' common/device_font_payload_build.py
! grep -A20 '^_luoshu_coloros_root_pairs()' common/coloros_global.sh | grep -Eq '/vendor/fonts|/odm/fonts|/oem/fonts|/oplus_'
grep -q 'ColorOS 原厂模板不可用' common/device_font_payload_policy.sh
! grep -q '请先恢复系统默认字体并完整重启一次' common/device_font_payload_policy.sh
grep -q 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt
! grep -A12 'fun rebootDevice()' android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt | grep -q 'operationBusy || mixState.busy'
echo 'v4 device regression guards passed'
''')
