#!/usr/bin/env python3
"""One-shot migration for font consistency and payload source hygiene."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def replace_required(path: str, old: str, new: str) -> None:
    text = read(path)
    if old not in text:
        raise SystemExit(f"missing replacement anchor in {path}: {old[:80]!r}")
    write(path, text.replace(old, new))


def clean_headers() -> None:
    replacements = {
        "common/util_functions.sh": (
            "# 版本：v13.4 Beta2 Hotfix6",
            "# 版本：v2.0.0",
        ),
        "common/font_import.sh": (
            "# 洛书 v13.4 Beta2 Hotfix6 - 安全 ZIP 字体包导入",
            "# 洛书 v2.0.0 - 安全 ZIP 字体包导入",
        ),
        "common/font_check.sh": (
            "# LuoShu v13.4 Beta2 Hotfix6 - 字体文件真实格式与基础兼容性检测",
            "# LuoShu v2.0.0 - 字体文件真实格式与基础兼容性检测",
        ),
        "common/font_switch_task.sh": (
            "# 洛书 v14：轻量字体切换桥。状态查询不会重复扫描字体索引。",
            "# 洛书 v2.0.0：轻量字体切换任务。状态查询不会重复扫描字体索引。",
        ),
        "common/module_status.sh": (
            "# 洛书 v14：在 Root 管理器中显示简洁的当前字体状态。",
            "# 洛书 v2.0.0：在 Root 管理器中显示简洁的当前字体状态。",
        ),
    }
    for path, (old, new) in replacements.items():
        replace_required(path, old, new)


def trim_dead_util_functions() -> None:
    path = "common/util_functions.sh"
    text = read(path)

    mono_start = text.find("# ============================================================\n# 判断字体文件是否为等宽字体")
    variable_start = text.find("# ============================================================\n# 判断字体是否为可变字体")
    if mono_start < 0 or variable_start < 0 or variable_start <= mono_start:
        raise SystemExit("util_functions monospace/serif cleanup anchors missing")
    text = text[:mono_start] + text[variable_start:]

    dead_start = text.find("# ============================================================\n# 读取字体配置")
    if dead_start < 0:
        raise SystemExit("util_functions dead legacy block anchor missing")
    text = text[:dead_start].rstrip() + "\n"
    write(path, text)


def update_rom_fallback() -> None:
    path = "common/rom_adapters.sh"
    text = read(path)
    text = text.replace(
        "# 统一维护各 ROM 的字体文件名表和覆盖逻辑，被 customize.sh 和 font_manager.sh 共同引用\n"
        "# 消除此前 copy_as_coloros() 在两个文件中重复定义、容易改一处漏一处的问题",
        "# 提供通用 ROM 回退映射；ColorOS、HyperOS、OriginOS 与 Flyme 的分区感知增强层会在运行时覆盖对应入口。",
    )
    text = text.replace(
        "# 未覆盖：Oplus-Serif.ttf / OplusOSUI-XThin.ttf（低优先级，影响面很小，暂不处理）\n"
        "# 注：get_all_coloros_names() 的定义保留在 util_functions.sh（唯一来源），\n"
        "# 这里不重复定义，避免两份列表将来改一处漏一处\n",
        "# 分区感知映射由 coloros_global.sh 负责；这里仅保留缺少增强层时的最小回退。\n",
    )
    pattern = re.compile(r"(_coloros_extra_names\(\) \{\n.*?\n\})", re.S)
    match = pattern.search(text)
    if not match:
        raise SystemExit("rom_adapters ColorOS fallback anchor missing")
    fallback = r'''

if ! type get_all_coloros_names >/dev/null 2>&1; then
    get_all_coloros_names() {
        printf '%s\n' "SysSans-Hant-Regular SysSans-Hans-Regular SysFont-Static-Regular SysFont-Hant-Regular SysFont-Hans-Regular SysFont-Regular SysSans-En-Regular $(_coloros_extra_names)"
    }
fi'''
    text = text[: match.end()] + fallback + text[match.end() :]
    write(path, text)


def improve_coloros_mapping() -> None:
    path = "common/coloros_global.sh"
    text = read(path)

    root_anchor = """_luoshu_coloros_root_pairs() {
    _lcg_module=\"$(_luoshu_coloros_module_dir)\"
"""
    if root_anchor not in text:
        raise SystemExit("coloros root-pair anchor missing")

    vendor_anchor = """_coloros_vendor_files() {
    printf '%s\\n' 'SysSans-En-Bold.ttf"""
    if vendor_anchor not in text:
        raise SystemExit("coloros vendor anchor missing")

    google_end = """_coloros_google_text_files() {
    printf '%s\\n' 'GoogleSansText-Regular.ttf GoogleSansText-Medium.ttf GoogleSansText-SemiBold.ttf GoogleSansText-Bold.ttf GoogleSansText-VF.ttf GoogleSansTextVF.ttf GoogleSans-Regular.ttf GoogleSans-Medium.ttf GoogleSans-SemiBold.ttf GoogleSans-Bold.ttf GoogleSans-VF.ttf GoogleSansFlex-Regular.ttf Roboto-Regular.ttf Roboto-Medium.ttf Roboto-SemiBold.ttf Roboto-Bold.ttf Roboto-Light.ttf Roboto-Thin.ttf Roboto-ExtraLight.ttf Roboto-ExtraBold.ttf Roboto-Black.ttf RobotoFlex-Regular.ttf RobotoStatic-Regular.ttf'
}
"""
    if google_end not in text:
        raise SystemExit("coloros Google font block anchor missing")

    oem_block = r'''

# ColorOS 16 and newer may request these physical UI slots directly instead of resolving a named XML
# family. Every entry is still existence-gated, so adding future-compatible names does not create
# unnecessary mount nodes on older devices.
_coloros_oem_ui_files() {
    printf '%s\n' 'OplusOSUI-XThin.ttf OplusOSUI-Thin.ttf OplusOSUI-ExtraLight.ttf OplusOSUI-Light.ttf OplusOSUI-Regular.ttf OplusOSUI-Medium.ttf OplusOSUI-SemiBold.ttf OplusOSUI-Bold.ttf OplusOSUI-ExtraBold.ttf OplusOSUI-Black.ttf OplusSans-Thin.ttf OplusSans-ExtraLight.ttf OplusSans-Light.ttf OplusSans-Regular.ttf OplusSans-Medium.ttf OplusSans-SemiBold.ttf OplusSans-Bold.ttf OplusSans-ExtraBold.ttf OplusSans-Black.ttf OppoSans-Thin.ttf OppoSans-Light.ttf OppoSans-Regular.ttf OppoSans-Medium.ttf OppoSans-SemiBold.ttf OppoSans-Bold.ttf OppoSans-ExtraBold.ttf OppoSans-Black.ttf'
}

# Discover safe upright UI slots from every real OPlus partition. This covers renamed files introduced
# by an OTA without replacing serif, emoji, symbols, monospace, icons or true italic faces.
_coloros_discovered_ui_files() {
    while IFS='|' read -r _lcg_real _lcg_overlay; do
        [ -d "$_lcg_real" ] || continue
        for _lcg_path in "$_lcg_real"/*.ttf; do
            [ -f "$_lcg_path" ] || continue
            _lcg_name=${_lcg_path##*/}
            case "$_lcg_name" in
                *Italic*|*Oblique*|*Serif*|*Mono*|*Emoji*|*Symbol*|*Icon*|*Clock*) continue ;;
            esac
            case "$_lcg_name" in
                SysFont*.ttf|SysSans*.ttf|OplusSans*.ttf|OplusOSUI*.ttf|OppoSans*.ttf|Opposans*.ttf|OPSans*.ttf|GoogleSans*.ttf|Roboto*.ttf|SourceSansPro*.ttf|DIN*.ttf|OPPODIN*.ttf)
                    printf '%s\n' "$_lcg_name"
                    ;;
            esac
        done
    done <<EOF_LUOSHU_COLOROS_DISCOVERY
$(_luoshu_coloros_root_pairs)
EOF_LUOSHU_COLOROS_DISCOVERY
}
'''
    text = text.replace(google_end, google_end + oem_block)

    old_get_all = """get_all_coloros_files() {
    printf '%s %s %s\\n' \"$(_coloros_core_files)\" \"$(_coloros_google_text_files)\" \"$(_coloros_vendor_files)\"
}
"""
    new_get_all = r'''get_all_coloros_files() {
    {
        for _lcg_list in "$(_coloros_core_files)" "$(_coloros_google_text_files)" "$(_coloros_vendor_files)" "$(_coloros_oem_ui_files)"; do
            for _lcg_file in $_lcg_list; do printf '%s\n' "$_lcg_file"; done
        done
        _coloros_discovered_ui_files
    } | awk 'NF && !seen[$0]++'
}
'''
    if old_get_all not in text:
        raise SystemExit("coloros get_all block anchor missing")
    text = text.replace(old_get_all, new_get_all)
    write(path, text)


def instantiate_variable_weights() -> None:
    path = "common/font_config_weights.sh"
    text = read(path)
    old = """    _lcw_tool=\"$_lcw_module/common/font_name_normalize.py\"
    _lcw_raw=\"${_lcw_output}.raw\"
    rm -f \"$_lcw_output\" \"$_lcw_raw\" 2>/dev/null || true
    cp -f \"$_lcw_source\" \"$_lcw_raw\" 2>/dev/null || return 1

    # A TTC may contain locale-specific faces. The generated XML points to one deterministic static
"""
    new = """    _lcw_tool=\"$_lcw_module/common/font_name_normalize.py\"
    _lcw_instance=\"$_lcw_module/common/font_instance.py\"
    _lcw_raw=\"${_lcw_output}.raw\"
    rm -f \"$_lcw_output\" \"$_lcw_raw\" 2>/dev/null || true

    # A direct variable-font application must materialize real 100-900 outlines. Merely changing the
    # OS/2 weight metadata leaves every Android weight visually identical and is a major source of
    # inconsistent hierarchy between titles, body text, keyboards and app controls.
    if type is_variable_font >/dev/null 2>&1 && is_variable_font \"$_lcw_source\" && \\
       [ -f \"$_lcw_instance\" ] && type _luoshu_font_config_exec >/dev/null 2>&1; then
        _luoshu_font_config_exec \"$_lcw_instance\" --input \"$_lcw_source\" --output \"$_lcw_raw\" \\
            --role cjk --weight \"$_lcw_weight\" --axes \"wght=$_lcw_weight\" >/dev/null 2>&1 || {
            rm -f \"$_lcw_raw\" \"$_lcw_output\" 2>/dev/null || true
            return 1
        }
    else
        cp -f \"$_lcw_source\" \"$_lcw_raw\" 2>/dev/null || return 1
    fi

    # A TTC may contain locale-specific faces. The generated XML points to one deterministic static
"""
    if old not in text:
        raise SystemExit("font_config_weights variable instancing anchor missing")
    write(path, text.replace(old, new))


def remove_runtime_webui_cache_paths() -> None:
    path = "common/font_manager.sh"
    text = read(path)
    old = """invalidate_font_index_cache() {
    rm -f \"$FONT_INDEX_JSON\" \"$FONT_INDEX_KEY\" \\
          \"$CONFIG_DIR/webui_font_list.json\" \"$CONFIG_DIR/webui_font_list.key\" 2>/dev/null || true
}
"""
    new = """invalidate_font_index_cache() {
    rm -f \"$FONT_INDEX_JSON\" \"$FONT_INDEX_KEY\" 2>/dev/null || true
}
"""
    if old not in text:
        raise SystemExit("font_manager cache anchor missing")
    write(path, text.replace(old, new))

    for path in ("common/native_import.sh", "common/font_import.sh"):
        text = read(path)
        text = re.sub(r"\n?\s*\"?\$[^\n]*webui_font_list\.(?:json|key)[^\n]*\n", "\n", text)
        text = text.replace("WebUI 名称", "App 显示名称")
        text = text.replace("供 WebUI", "供原生 App")
        write(path, text)


def remove_unused_report() -> None:
    path = ROOT / "common/font_report.sh"
    if not path.exists():
        raise SystemExit("font_report.sh already missing; migration assumptions changed")
    path.unlink()


def add_payload_manifest() -> None:
    common_files = """
common/app_bridge.sh
common/app_installer.sh
common/background_task.sh
common/coloros_global.sh
common/composite_font.py
common/font_axis_info.py
common/font_check.sh
common/font_config_overlay.py
common/font_config_partitions.sh
common/font_config_runtime.sh
common/font_config_targets.py
common/font_config_weights.sh
common/font_coverage.py
common/font_coverage.sh
common/font_coverage_info.py
common/font_details.sh
common/font_extract_faces.py
common/font_import.sh
common/font_import_compat.sh
common/font_import_probe.py
common/font_instance.py
common/font_library_cache.sh
common/font_manager.sh
common/font_metadata.py
common/font_mix.sh
common/font_mix_controller.sh
common/font_name_normalize.py
common/font_role_check.py
common/font_role_check.sh
common/font_safety.sh
common/font_switch_task.sh
common/hyperos_global.sh
common/luoshu_cli.sh
common/luoshu_composite.sh
common/mix_task_handoff.sh
common/mix_weight_mode.sh
common/module_status.sh
common/module_update_state.sh
common/mount_compat.sh
common/multiweight_mix_task.sh
common/native_import.sh
common/origin_flyme_global.sh
common/rom_adapters.sh
common/util_functions.sh
common/weighted_mix_task.sh
common/python
""".strip()
    roots = """
config
fonts
system
licenses
LICENSE
NOTICE.md
THIRD_PARTY_NOTICES.md
README.md
README.txt
CHANGELOG.md
customize.sh
module.prop
post-fs-data.sh
service.sh
uninstall.sh
action.sh
magic
兼容与目录说明.txt
""".strip()
    manifest = "# Explicit release payload. New runtime files must be reviewed and listed here.\n" + common_files + "\n" + roots + "\n"
    write("scripts/module_payload_manifest.txt", manifest)


def update_build_script() -> None:
    path = "scripts/build.sh"
    text = read(path)
    old = """rm -rf \"$STAGE\"
mkdir -p \"$STAGE\" \"$OUT\"
for path in common config fonts system licenses LICENSE NOTICE.md THIRD_PARTY_NOTICES.md README.md README.txt CHANGELOG.md customize.sh module.prop post-fs-data.sh service.sh uninstall.sh action.sh magic 兼容与目录说明.txt; do
  [ ! -e \"$ROOT/$path\" ] || cp -a \"$ROOT/$path\" \"$STAGE/\"
done
"""
    new = """rm -rf \"$STAGE\"
mkdir -p \"$STAGE\" \"$OUT\"
PAYLOAD_MANIFEST=\"$ROOT/scripts/module_payload_manifest.txt\"
test -s \"$PAYLOAD_MANIFEST\"
while IFS= read -r path || [ -n \"$path\" ]; do
  case \"$path\" in ''|\\#*) continue ;; esac
  [ -e \"$ROOT/$path\" ] || { echo \"Missing payload manifest entry: $path\" >&2; exit 69; }
  mkdir -p \"$(dirname \"$STAGE/$path\")\"
  cp -a \"$ROOT/$path\" \"$STAGE/$path\"
done < \"$PAYLOAD_MANIFEST\"
"""
    if old not in text:
        raise SystemExit("build payload-copy anchor missing")
    write(path, text.replace(old, new))


def add_tests() -> None:
    coloros_test = r'''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-coloros-consistency)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
PUBLIC="$TMP/public"
REAL_SYSTEM="$TMP/real-system"
REAL_PRODUCT="$TMP/real-product"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$PUBLIC/fonts" "$REAL_SYSTEM" "$REAL_PRODUCT"
cp "$ROOT/common/util_functions.sh" "$MODULE/common/util_functions.sh"
cp "$ROOT/common/rom_adapters.sh" "$MODULE/common/rom_adapters.sh"
cp "$ROOT/common/coloros_global.sh" "$MODULE/common/coloros_global.sh"

python3 - "$PUBLIC/fonts/Demo-Regular.ttf" "$PUBLIC/fonts/Demo-Thin.ttf" "$PUBLIC/fonts/Demo-SemiBold.ttf" <<'PY'
from pathlib import Path
import sys
for index, name in enumerate(sys.argv[1:], 1):
    Path(name).write_bytes((f'font-{index}-'.encode() * 700)[:5000])
PY
for name in OplusOSUI-XThin.ttf OplusSans-SemiBold.ttf GoogleSansText-Regular.ttf Oplus-Serif.ttf Roboto-Italic.ttf; do
    : > "$REAL_PRODUCT/$name"
done

MODULE_DIR="$MODULE"
LUOSHU_PUBLIC_DIR="$PUBLIC"
USER_FONTS_DIR="$PUBLIC/fonts"
. "$MODULE/common/util_functions.sh"
. "$MODULE/common/rom_adapters.sh"
LUOSHU_COLOROS_SYSTEM_FONTS_ROOT="$REAL_SYSTEM"
LUOSHU_COLOROS_PRODUCT_FONTS_ROOT="$REAL_PRODUCT"
LUOSHU_COLOROS_SYSTEM_EXT_FONTS_ROOT="$TMP/none-system-ext"
LUOSHU_COLOROS_VENDOR_FONTS_ROOT="$TMP/none-vendor"
LUOSHU_COLOROS_ODM_FONTS_ROOT="$TMP/none-odm"
LUOSHU_COLOROS_OEM_FONTS_ROOT="$TMP/none-oem"
LUOSHU_COLOROS_MY_PRODUCT_FONTS_ROOT="$TMP/none-my-product"
LUOSHU_COLOROS_OPLUS_PRODUCT_FONTS_ROOT="$TMP/none-oplus-product"
LUOSHU_COLOROS_OPLUS_ENGINEERING_FONTS_ROOT="$TMP/none-oplus-engineering"
LUOSHU_COLOROS_OPLUS_VERSION_FONTS_ROOT="$TMP/none-oplus-version"
LUOSHU_COLOROS_OPLUS_REGION_FONTS_ROOT="$TMP/none-oplus-region"
. "$MODULE/common/coloros_global.sh"

copy_as_coloros "$PUBLIC/fonts/Demo-Regular.ttf" "$MODULE/system/fonts" quick Demo
cmp -s "$PUBLIC/fonts/Demo-Thin.ttf" "$MODULE/product/fonts/OplusOSUI-XThin.ttf"
cmp -s "$PUBLIC/fonts/Demo-SemiBold.ttf" "$MODULE/product/fonts/OplusSans-SemiBold.ttf"
cmp -s "$PUBLIC/fonts/Demo-Regular.ttf" "$MODULE/product/fonts/GoogleSansText-Regular.ttf"
test ! -e "$MODULE/product/fonts/Oplus-Serif.ttf"
test ! -e "$MODULE/product/fonts/Roboto-Italic.ttf"
echo 'ColorOS consistency mapping passed.'
'''
    write("scripts/coloros_consistency_mapping_test.sh", coloros_test)

    variable_test = r'''#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
TMP=$(mktemp -d 2>/dev/null || mktemp -d -t luoshu-variable-weights)
trap 'rm -rf "$TMP"' EXIT HUP INT TERM
MODULE="$TMP/module"
mkdir -p "$MODULE/common" "$MODULE/system/fonts" "$MODULE/config"
cp "$ROOT/common/font_config_weights.sh" "$MODULE/common/font_config_weights.sh"
printf 'variable-source-%05000d' 1 > "$TMP/source.ttf"
: > "$TMP/calls"
MODULE_DIR="$MODULE"
is_variable_font() { return 0; }
_luoshu_font_config_exec() {
    script="$1"; shift
    printf '%s %s\n' "${script##*/}" "$*" >> "$TMP/calls"
    input=''; output=''
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --input) input="$2"; shift 2 ;;
            --output) output="$2"; shift 2 ;;
            *) shift ;;
        esac
    done
    cp -f "$input" "$output"
}
. "$MODULE/common/font_config_weights.sh"
_luoshu_config_normalize_weight "$TMP/source.ttf" "$TMP/LuoShu-700.ttf" 700
test -s "$TMP/LuoShu-700.ttf"
grep -q 'font_instance.py .*--role cjk .*--weight 700 .*--axes wght=700' "$TMP/calls"
grep -q 'font_name_normalize.py .*--weight 700' "$TMP/calls"
echo 'Variable direct-apply weight materialization passed.'
'''
    write("scripts/font_config_variable_weight_test.sh", variable_test)


def update_checks() -> None:
    path = "scripts/check.sh"
    text = read(path)
    text = text.replace(
        "scripts/build.sh scripts/version.sh scripts/prepare_composite_runtime.sh scripts/mount_compat_test.sh \\",
        "scripts/build.sh scripts/version.sh scripts/module_payload_manifest.txt scripts/prepare_composite_runtime.sh scripts/mount_compat_test.sh \\",
    )
    text = text.replace(
        "scripts/app_installer_test.sh scripts/hyperos_global_mapping_test.sh \\",
        "scripts/app_installer_test.sh scripts/hyperos_global_mapping_test.sh scripts/coloros_consistency_mapping_test.sh scripts/font_config_variable_weight_test.sh \\",
    )

    anchor = "# 单包构建必须显式传入 APK；Debug 包只能由测试工作流明确放行。"
    manifest_gate = r'''# 发布包使用显式清单。common/ 新增运行文件必须被审查后列入，不能再整目录复制。
PAYLOAD_MANIFEST="$ROOT/scripts/module_payload_manifest.txt"
test -s "$PAYLOAD_MANIFEST"
awk 'NF && $1 !~ /^#/ { if (seen[$0]++) exit 1 }' "$PAYLOAD_MANIFEST"
while IFS= read -r payload || [ -n "$payload" ]; do
  case "$payload" in ''|\#*) continue ;; esac
  test -e "$ROOT/$payload"
done < "$PAYLOAD_MANIFEST"
find "$ROOT/common" -maxdepth 1 -type f -printf 'common/%f\n' | sort > /tmp/luoshu-common-files.txt
grep '^common/' "$PAYLOAD_MANIFEST" | grep -v '^common/python$' | sort > /tmp/luoshu-manifest-common.txt
cmp -s /tmp/luoshu-common-files.txt /tmp/luoshu-manifest-common.txt

# 活跃运行时代码不得再出现历史开发版本头、WebUI 函数或未使用的报告脚本。
! grep -RInE --exclude-dir=python '(^|[^0-9])v1[34](\.|[^0-9])|Beta[[:space:]]*[0-9]|Hotfix' \
  "$ROOT/common" "$ROOT/customize.sh" "$ROOT/post-fs-data.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" >/dev/null 2>&1
! grep -qE 'get_all_fonts_json|get_font_info_json|scan_installed_families|refresh_font_cache' "$ROOT/common/util_functions.sh"
test ! -e "$ROOT/common/font_report.sh"
! grep -RInE 'webui_font_list|WebUI' "$ROOT/common" --exclude=module_update_state.sh >/dev/null 2>&1

'''
    if anchor not in text:
        raise SystemExit("check manifest insertion anchor missing")
    text = text.replace(anchor, manifest_gate + anchor)
    text = text.replace(
        'sh "$ROOT/scripts/hyperos_global_mapping_test.sh"\n',
        'sh "$ROOT/scripts/hyperos_global_mapping_test.sh"\nsh "$ROOT/scripts/coloros_consistency_mapping_test.sh"\nsh "$ROOT/scripts/font_config_variable_weight_test.sh"\n',
    )
    write(path, text)


def update_docs() -> None:
    for path in ("README.md", "README.txt"):
        text = read(path)
        note = (
            "\n- **应用内置字体边界**：输入法键帽、QQ/微信等应用自带字体、图片或贴纸文字、"
            "以及部分 WebView 页面不经过 Android 系统字体映射；无 Hook 模块无法强制替换这些资源。\n"
            if path.endswith(".md")
            else "\n- 应用内置字体边界：输入法键帽、应用自带字体、图片文字和部分 WebView 不经过系统字体映射，无 Hook 模块无法强制替换。\n"
        )
        if "应用内置字体边界" not in text:
            text = text.rstrip() + "\n" + note
        write(path, text)

    path = "CHANGELOG.md"
    text = read(path)
    bullets = (
        "- ColorOS 按真实分区自动发现 OplusOSUI/OplusSans 等安全 UI 字体槽，减少同页仍显示原厂字体的情况。\n"
        "- 可变字体直接应用时真正实例化 100–900 九档轮廓，不再只修改字重元数据。\n"
        "- 构建改用显式 payload 清单，删除无调用报告脚本、WebUI 运行时函数和历史版本头。\n"
    )
    if bullets.splitlines()[0] not in text:
        marker = "## [Unreleased]\n"
        if marker in text:
            text = text.replace(marker, marker + "\n" + bullets, 1)
        else:
            text = "## [Unreleased]\n\n" + bullets + "\n" + text
    write(path, text)


def verify() -> None:
    required = [
        "scripts/module_payload_manifest.txt",
        "scripts/coloros_consistency_mapping_test.sh",
        "scripts/font_config_variable_weight_test.sh",
    ]
    for name in required:
        if not (ROOT / name).is_file():
            raise SystemExit(f"missing generated file: {name}")
    if (ROOT / "common/font_report.sh").exists():
        raise SystemExit("unused font_report.sh survived")
    util = read("common/util_functions.sh")
    for forbidden in ("get_all_fonts_json", "get_font_info_json", "refresh_font_cache", "v13.4"):
        if forbidden in util:
            raise SystemExit(f"stale util symbol survived: {forbidden}")
    coloros = read("common/coloros_global.sh")
    for required_text in ("OplusOSUI-XThin.ttf", "_coloros_discovered_ui_files", "OplusSans-SemiBold.ttf"):
        if required_text not in coloros:
            raise SystemExit(f"ColorOS consistency feature missing: {required_text}")
    weights = read("common/font_config_weights.sh")
    if "--axes \"wght=$_lcw_weight\"" not in weights:
        raise SystemExit("variable direct-apply instancing missing")


def main() -> None:
    clean_headers()
    trim_dead_util_functions()
    update_rom_fallback()
    improve_coloros_mapping()
    instantiate_variable_weights()
    remove_runtime_webui_cache_paths()
    remove_unused_report()
    add_payload_manifest()
    update_build_script()
    add_tests()
    update_checks()
    update_docs()
    verify()


if __name__ == "__main__":
    main()
