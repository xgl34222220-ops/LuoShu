#!/system/bin/sh
set -eu
ROOT="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
VM="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
PREVIEW="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/NativeFontPreview.kt"
LIBRARY="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/library/FontLibraryScreenCompact.kt"
BRIDGE="$ROOT/common/app_bridge.sh"
SHELL="$ROOT/android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuAppShell.kt"

grep -q 'else -> Unit // 本地索引优先' "$VM"
grep -q 'preview_export_batch' "$VM"
grep -q 'rootFallback: Boolean = true' "$PREVIEW"
grep -q 'rootFallback = false' "$LIBRARY"
grep -q 'preview_export_batch)' "$BRIDGE"
! grep -A3 'LaunchedEffect(Unit)' "$SHELL" | grep -q 'refreshSystemWeight()'
printf '%s\n' 'app font loading performance checks passed'
