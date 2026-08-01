#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
APP="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu"

LIB_ROUTE="$APP/ui/library/FontLibraryRoute.kt"
LIB_MIUIX="$APP/ui/library/FontLibraryScreenMiuix.kt"
LIB_MATERIAL="$APP/ui/library/FontLibraryScreenCompact.kt"
MANAGE_MIUIX="$APP/ui/library/FontLibraryManagementMiuix.kt"
IMPORT_ROUTE="$APP/NativeImportOverlay.kt"
IMPORT_MIUIX="$APP/NativeImportOverlayMiuix.kt"
IMPORT_MATERIAL="$APP/NativeImportOverlayMaterial.kt"
STUDIO_ROUTE="$APP/ui/studio/FontStudioRoute.kt"
STUDIO_MIUIX="$APP/ui/studio/FontStudioScreenMiuixNative.kt"
STUDIO_MATERIAL="$APP/ui/studio/FontStudioScreenMaterial.kt"
STUDIO_AXIS_MIUIX="$APP/ui/studio/StudioAxisControlsMiuix.kt"
STUDIO_TOOLS_MIUIX="$APP/ui/studio/StudioToolLauncherMiuix.kt"
STUDIO_NOTICE_MIUIX="$APP/ui/studio/StudioRestoreNoticeMiuix.kt"
SETTINGS_ROUTE="$APP/ui/settings/AppearanceSettingsScreen.kt"
SETTINGS_MIUIX="$APP/ui/settings/AppearanceSettingsMiuix.kt"
SETTINGS_MATERIAL="$APP/ui/settings/AppearanceSettingsScreen.kt"
LOGS_ROUTE="$APP/ui/logs/LogsRoute.kt"
LOGS_MIUIX="$APP/ui/logs/LogsScreenMiuix.kt"
LOGS_MATERIAL="$APP/ui/logs/LogsScreenCompact.kt"
LOGS_OVERLAYS_MIUIX="$APP/ui/logs/LogsMiuixOverlays.kt"
IMPORT_CONTROLS_MATERIAL="$APP/ui/logs/ImportTaskControls.kt"
DIAGNOSTIC_MATERIAL="$APP/ui/logs/DiagnosticExportUi.kt"

# Theme routing must be explicit. Shared files own state and actions only.
grep -q 'UiStyle.MIUIX -> FontLibraryScreenMiuix' "$LIB_ROUTE"
grep -q 'UiStyle.MATERIAL -> FontLibraryScreenCompact' "$LIB_ROUTE"
grep -q 'FontLibraryManagementButtonMiuix' "$LIB_ROUTE"
grep -q 'FontLibraryManagementDialogMiuix' "$LIB_ROUTE"
grep -q 'style = UiStyle.MATERIAL' "$LIB_ROUTE"
grep -q 'UiStyle.MIUIX -> NativeImportOverlayMiuix' "$IMPORT_ROUTE"
grep -q 'UiStyle.MATERIAL -> NativeImportOverlayMaterial' "$IMPORT_ROUTE"
grep -q 'UiStyle.MIUIX -> StudioToolLauncherMiuix' "$STUDIO_ROUTE"
grep -q 'UiStyle.MATERIAL -> StudioToolLauncher' "$STUDIO_ROUTE"
grep -q 'UiStyle.MIUIX -> FontStudioScreenMiuixNative' "$STUDIO_ROUTE"
grep -q 'UiStyle.MATERIAL -> FontStudioScreenMaterial' "$STUDIO_ROUTE"
grep -q 'UiStyle.MIUIX -> StudioRestoreNoticeMiuix' "$STUDIO_ROUTE"
grep -q 'UiStyle.MIUIX -> AppearanceSettingsMiuix' "$SETTINGS_ROUTE"
grep -q 'UiStyle.MATERIAL -> AppearanceSettingsMaterial' "$SETTINGS_ROUTE"
grep -q 'UiStyle.MIUIX -> LogsScreenMiuix' "$LOGS_ROUTE"
grep -q 'UiStyle.MATERIAL -> LogsScreenCompact' "$LOGS_ROUTE"
grep -q 'UiStyle.MIUIX -> ImportTaskControlsMiuix' "$LOGS_ROUTE"
grep -q 'UiStyle.MATERIAL -> ImportTaskControls' "$LOGS_ROUTE"
grep -q 'UiStyle.MIUIX -> DiagnosticExportDialogMiuix' "$LOGS_ROUTE"
grep -q 'UiStyle.MATERIAL -> DiagnosticExportDialog' "$LOGS_ROUTE"

# Native Miuix trees may use Foundation, icons and shared business widgets, but
# never Material 3 controls or the hand-built LuoShu Material component layer.
for file in \
    "$LIB_MIUIX" \
    "$MANAGE_MIUIX" \
    "$IMPORT_MIUIX" \
    "$STUDIO_MIUIX" \
    "$STUDIO_AXIS_MIUIX" \
    "$STUDIO_TOOLS_MIUIX" \
    "$STUDIO_NOTICE_MIUIX" \
    "$SETTINGS_MIUIX" \
    "$LOGS_MIUIX" \
    "$LOGS_OVERLAYS_MIUIX"; do
    grep -q 'top.yukonga.miuix.kmp' "$file"
    ! grep -q 'androidx.compose.material3' "$file"
    ! grep -q 'io.github.xgl34222220.luoshu.ui.design.LuoShu' "$file"
done

grep -q 'top.yukonga.miuix.kmp.basic.TextField' "$LIB_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.BasicComponent' "$LIB_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.Checkbox' "$MANAGE_MIUIX"
grep -q 'top.yukonga.miuix.kmp.overlay.OverlayDialog' "$MANAGE_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.LinearProgressIndicator' "$IMPORT_MIUIX"
grep -q 'top.yukonga.miuix.kmp.overlay.OverlayDialog' "$IMPORT_MIUIX"
grep -q 'StudioAxisControlsMiuix' "$STUDIO_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.LinearProgressIndicator' "$STUDIO_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.Slider' "$STUDIO_AXIS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.overlay.OverlayDialog' "$STUDIO_TOOLS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.overlay.OverlayDialog' "$STUDIO_NOTICE_MIUIX"
grep -q 'top.yukonga.miuix.kmp.preference.SwitchPreference' "$SETTINGS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.preference.RadioButtonPreference' "$SETTINGS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.BasicComponent' "$SETTINGS_MIUIX"
grep -q 'private enum class MiuixLogsTab' "$LOGS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.BasicComponent' "$LOGS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.basic.LinearProgressIndicator' "$LOGS_MIUIX"
grep -q 'top.yukonga.miuix.kmp.overlay.OverlayDialog' "$LOGS_OVERLAYS_MIUIX"
grep -q 'ImportTaskControlsMiuix' "$LOGS_OVERLAYS_MIUIX"
grep -q 'DiagnosticExportDialogMiuix' "$LOGS_OVERLAYS_MIUIX"

# Material implementations remain separate and continue using Material 3.
grep -q 'androidx.compose.material3' "$LIB_MATERIAL"
grep -q 'androidx.compose.material3' "$IMPORT_MATERIAL"
grep -q 'androidx.compose.material3' "$STUDIO_MATERIAL"
grep -q 'androidx.compose.material3' "$SETTINGS_MATERIAL"
grep -q 'androidx.compose.material3' "$LOGS_MATERIAL"
grep -q 'androidx.compose.material3' "$IMPORT_CONTROLS_MATERIAL"
grep -q 'androidx.compose.material3' "$DIAGNOSTIC_MATERIAL"

echo 'Miuix and Material home, font-library, font-studio, settings and task-center render trees are isolated.'
