#!/usr/bin/env python3
"""One-shot source migration from historical v14 filenames to the v2 namespace."""
from __future__ import annotations

import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RENAMES = {
    "common/v14_mix.sh": "common/font_mix_controller.sh",
    "common/v142_weighted_mix.sh": "common/weighted_mix_task.sh",
    "common/v143_auto_multiweight_mix.sh": "common/multiweight_mix_task.sh",
    "common/v14_switch.sh": "common/font_switch_task.sh",
    "scripts/rc3_audit.sh": "scripts/v2_source_audit.sh",
}

OBSOLETE = {
    "common/play_font_bridge",
    "common/wechat_xweb_bridge",
    "common/volume_key.sh",
    "common/legacy_data_fonts_cleanup.sh",
}

REPLACEMENTS = {
    "v143_auto_multiweight_mix.sh": "multiweight_mix_task.sh",
    "v142_weighted_mix.sh": "weighted_mix_task.sh",
    "v14_mix.sh": "font_mix_controller.sh",
    "v14_switch.sh": "font_switch_task.sh",
    "rc3_audit.sh": "v2_source_audit.sh",
    "# 洛书 v14.3.9：字体组合轻量桥。": "# 洛书 v2.0.0：字体组合控制器。",
    "# 洛书 v14.2 RC2：异步真实字重与多轴字体组合桥。": "# 洛书 v2.0.0：异步真实字重与多轴字体组合任务。",
    "# 任务状态持久化在模块目录，App 或 WebUI 退出后可重新接管。": "# 任务状态持久化在模块目录，原生 App 退出后仍可重新接管。",
    "# 洛书 v14.3.9：组合页自动多字重复合引擎。": "# 洛书 v2.0.0：自动多字重复合任务。",
    "# 洛书 v14.3 Alpha1.4 原生 App 核心桥：状态、字体库、文件导入、预览、切换与复合任务接口。": "# 洛书 v2.0.0 原生 App 核心桥：状态、字体库、导入、预览、切换与复合任务接口。",
    "# 洛书 v14.3 Alpha1.5：按字体族定位真实源文件并输出字形覆盖诊断。": "# 洛书 v2.0.0：按字体族定位真实源文件并输出字形覆盖诊断。",
    "# 洛书 v14.3 Alpha1：按现有字体族 ID 返回稳定文件身份与 TTC 字体面详情。": "# 洛书 v2.0.0：按字体族 ID 返回稳定文件身份与 TTC 字体面详情。",
    "# 洛书 v14.3 Alpha1.1：原生 App 文件选择器导入桥。": "# 洛书 v2.0.0：原生 App 文件选择器导入桥。",
    "# 洛书 v14.1：完整复合字体引擎。": "# 洛书 v2.0.0：完整复合字体引擎。",
    "for LuoShu v14.2": "for LuoShu v2.0.0",
}

SKIP_DIRS = {".git", ".gradle", "build", "dist", ".runtime-work", "common/python"}
TEXT_SUFFIXES = {
    ".sh", ".py", ".kt", ".kts", ".md", ".txt", ".yml", ".yaml", ".conf", ".prop", ".json",
}


def is_skipped(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    return any(rel == item or rel.startswith(item + "/") for item in SKIP_DIRS)


def read_text(path: Path) -> str | None:
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"play_font_bridge", "wechat_xweb_bridge"}:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def write_if_changed(path: Path, text: str) -> None:
    old = path.read_text(encoding="utf-8")
    if old != text:
        path.write_text(text, encoding="utf-8")


def rename_sources() -> None:
    for old_name, new_name in RENAMES.items():
        old = ROOT / old_name
        new = ROOT / new_name
        if new.exists() and not old.exists():
            continue
        if not old.exists():
            raise SystemExit(f"missing rename source: {old_name}")
        new.parent.mkdir(parents=True, exist_ok=True)
        old.rename(new)


def delete_obsolete() -> None:
    for name in OBSOLETE:
        path = ROOT / name
        if path.exists():
            path.unlink()


def replace_repository_text() -> None:
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_skipped(path):
            continue
        text = read_text(path)
        if text is None:
            continue
        updated = text
        for old, new in REPLACEMENTS.items():
            updated = updated.replace(old, new)
        if updated != text:
            path.write_text(updated, encoding="utf-8")


def rewrite_uninstall() -> None:
    path = ROOT / "uninstall.sh"
    path.write_text(
        """#!/system/bin/sh
# 洛书 v2.0.0：安全卸载。只恢复洛书明确记录的系统设置，不触碰 /data/fonts。
set +e
MODDIR="${0%/*}"
MODULE_VERSION=$(sed -n 's/^version=//p' "$MODDIR/module.prop" 2>/dev/null | head -n1)
[ -n "$MODULE_VERSION" ] || MODULE_VERSION="unknown"

# 恢复安装洛书前记录的 Android 全局字体粗细设置。
if command -v settings >/dev/null 2>&1; then
    _fw_restore=0
    [ -f "$MODDIR/config/font_weight_original.conf" ] && \\
        _fw_restore=$(sed -n 's/^adjustment=//p' "$MODDIR/config/font_weight_original.conf" 2>/dev/null | head -n1)
    case "$_fw_restore" in ''|*[!0-9-]*) _fw_restore=0 ;; esac
    settings --user current put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || \\
        settings put secure font_weight_adjustment "$_fw_restore" >/dev/null 2>&1 || true
fi

# v2 使用 systemless 字体与 XML 负载，不删除 Android/OEM 管理的动态字体数据库。
rm -f "$MODDIR/.first_boot" "$MODDIR/.font_switch.lock" 2>/dev/null || true
mkdir -p "$MODDIR/logs" 2>/dev/null || true
echo "[$(date '+%Y-%m-%d %H:%M:%S' 2>/dev/null)] 洛书 $MODULE_VERSION 已卸载" >> "$MODDIR/logs/fontswitch.log" 2>/dev/null || true
exit 0
""",
        encoding="utf-8",
    )


def rewrite_compatibility_document() -> None:
    candidates = list(ROOT.glob("*兼容*目录*说明*.txt"))
    if not candidates:
        candidates = [ROOT / "兼容与目录说明.txt"]
    text = """洛书 v2.0.0

Android 无 Hook 全局字体引擎：
- 原生 Android App 负责字体导入、预览、组合、应用与任务恢复
- 中文字体作为完整基底，英文与数字只替换对应字形和度量
- 生成 100–900 九档静态字重，并保持 Emoji、图标、等宽和专用字体原样
- 基于设备原始 fonts.xml、font_fallback.xml 与 OEM 配置生成 systemless overlay
- 不直接修改只读系统分区，也不读写 Android 动态字体数据库 /data/fonts
- 字体负载经过生成、校验、暂存和原子提交，失败时保留旧有效配置
- 支持 Magisk、KernelSU、SukiSU Ultra、APatch 与 Mountify

用户字体目录：/sdcard/LuoShu/fonts
安全导入目录：/sdcard/LuoShu/import
诊断报告目录：/sdcard/LuoShu/reports
"""
    for path in candidates:
        path.write_text(text, encoding="utf-8")


def clean_customize() -> None:
    path = ROOT / "customize.sh"
    text = path.read_text(encoding="utf-8")
    text = text.replace(' "$MODPATH/common/play_font_bridge" "$MODPATH/common/wechat_xweb_bridge"', "")
    path.write_text(text, encoding="utf-8")


def update_build_gates() -> None:
    path = ROOT / "scripts/build.sh"
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'common/stability.sh common/fonts_xml_template.sh common/play_font_bridge.sh common/wechat_xweb_bridge.sh',
        'common/stability.sh common/fonts_xml_template.sh common/play_font_bridge common/wechat_xweb_bridge common/volume_key.sh common/legacy_data_fonts_cleanup.sh',
    )
    marker = "# Final payload gate: obsolete or WebUI paths must never return."
    if marker not in text:
        raise SystemExit("build gate marker missing")
    path.write_text(text, encoding="utf-8")


def update_readme_claims() -> None:
    replacements = {
        "- **不覆盖字体 XML**：不修改 `fonts.xml` 或 `font_fallback.xml`。":
            "- **保留原配置结构**：基于设备原始 `fonts.xml`、`font_fallback.xml` 与 OEM 配置生成经过验证的 systemless overlay，不直接修改系统分区。",
        "- 不覆盖 fonts.xml / font_fallback.xml":
            "- 基于设备原始字体 XML 生成并验证 systemless overlay，不修改系统分区原文件",
    }
    for name in ("README.md", "README.txt"):
        path = ROOT / name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for old, new in replacements.items():
            text = text.replace(old, new)
        path.write_text(text, encoding="utf-8")


def append_source_gates() -> None:
    path = ROOT / "scripts/check.sh"
    text = path.read_text(encoding="utf-8")
    gate = r'''
# v2 source namespace: old runtime filenames and obsolete bind-mount bridges must not return.
for obsolete in \
  common/v14_mix.sh common/v142_weighted_mix.sh common/v143_auto_multiweight_mix.sh common/v14_switch.sh \
  common/play_font_bridge common/wechat_xweb_bridge common/volume_key.sh common/legacy_data_fonts_cleanup.sh; do
  test ! -e "$ROOT/$obsolete"
done
for active in \
  common/font_mix_controller.sh common/weighted_mix_task.sh common/multiweight_mix_task.sh common/font_switch_task.sh \
  scripts/v2_source_audit.sh; do
  test -f "$ROOT/$active"
done
! grep -RInE 'common/(v14_mix|v142_weighted_mix|v143_auto_multiweight_mix|v14_switch)\\.sh' \
  "$ROOT" --exclude-dir=.git --exclude=CHANGELOG.md --exclude='RELEASE_NOTES_*' >/dev/null 2>&1
! grep -RInE '洛书 v1[34]\\.|LuoShu v1[34]\\.' \
  "$ROOT/common" "$ROOT/customize.sh" "$ROOT/post-fs-data.sh" "$ROOT/service.sh" "$ROOT/uninstall.sh" \
  --exclude-dir=python >/dev/null 2>&1
'''
    if "# v2 source namespace:" not in text:
        anchor = "# 许可证与声明保持完整。"
        if anchor not in text:
            raise SystemExit("check.sh insertion anchor missing")
        text = text.replace(anchor, gate + "\n" + anchor)
    path.write_text(text, encoding="utf-8")


def update_changelog() -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    section = """## [Unreleased]\n\n- 统一 Material 与 MIUIx 字体卡片样张，所有字体均显示相同的“洛书字体 / 天地玄黄 / Aa / Hello / 数字”两行预览。\n- 将 v14 历史运行时文件名收敛为 v2 语义命名，并同步 App、CLI、开机恢复、测试与构建门禁。\n- 删除未使用的 GMS/XWeb bind-mount bridge、音量键入口和旧动态字体清理脚本。\n- 卸载流程不再删除 `/data/fonts`，文档统一为原生 App-only 与 systemless XML overlay 架构。\n\n"""
    if "## [Unreleased]" not in text:
        first_heading = text.find("## ")
        if first_heading >= 0:
            text = text[:first_heading] + section + text[first_heading:]
        else:
            text += "\n" + section
    path.write_text(text, encoding="utf-8")


def verify() -> None:
    for old in RENAMES:
        if (ROOT / old).exists():
            raise SystemExit(f"old path still exists: {old}")
    for new in RENAMES.values():
        if not (ROOT / new).exists():
            raise SystemExit(f"new path missing: {new}")
    for old in OBSOLETE:
        if (ROOT / old).exists():
            raise SystemExit(f"obsolete path still exists: {old}")

    forbidden = re.compile(r"common/(?:v14_mix|v142_weighted_mix|v143_auto_multiweight_mix|v14_switch)\.sh")
    for path in ROOT.rglob("*"):
        if not path.is_file() or is_skipped(path) or path.name == "CHANGELOG.md" or path.name.startswith("RELEASE_NOTES_"):
            continue
        text = read_text(path)
        if text and forbidden.search(text):
            raise SystemExit(f"old runtime reference remains in {path.relative_to(ROOT)}")


def remove_one_shot_files() -> None:
    for name in ("scripts/v2_source_consolidation.py", ".github/workflows/v2-source-consolidation.yml"):
        path = ROOT / name
        if path.exists():
            path.unlink()


def main() -> None:
    rename_sources()
    delete_obsolete()
    replace_repository_text()
    rewrite_uninstall()
    rewrite_compatibility_document()
    clean_customize()
    update_build_gates()
    update_readme_claims()
    append_source_gates()
    update_changelog()
    verify()
    remove_one_shot_files()


if __name__ == "__main__":
    main()
