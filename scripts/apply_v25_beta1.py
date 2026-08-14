#!/usr/bin/env python3
from __future__ import annotations
import shutil
import sys
from pathlib import Path

WORK = Path(__file__).resolve().parents[1]
REPO = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()


def read(rel: str) -> str:
    return (REPO / rel).read_text(encoding='utf-8')


def write(rel: str, text: str) -> None:
    path = REPO / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, found {n}')
    return text.replace(old, new, 1)


def copy(rel: str) -> None:
    src = WORK / rel
    dst = REPO / rel
    if not src.is_file():
        raise SystemExit(f'missing overlay file: {src}')
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.resolve() != dst.resolve():
        shutil.copy2(src, dst)

# 1. Fix the Beta 1 compilation clash first.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SystemCenterViewModel.kt'
s = read(rel)
s = once(s, 'fun setUpdateChannel(channel: UpdateChannel)', 'fun selectUpdateChannel(channel: UpdateChannel)', rel)
write(rel, s)

# 2. Settings: add Backup page and use the non-clashing update action name.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/SettingsHubScreen.kt'
s = read(rel)
s = once(s, 'import androidx.compose.material.icons.rounded.Build\n', 'import androidx.compose.material.icons.rounded.Backup\nimport androidx.compose.material.icons.rounded.Build\n', rel + ': import')
s = once(s,
'''    SAFETY("安全", Icons.Rounded.Security),\n    UPDATE("更新", Icons.Rounded.SystemUpdate),''',
'''    SAFETY("安全", Icons.Rounded.Security),\n    BACKUP("备份", Icons.Rounded.Backup),\n    UPDATE("更新", Icons.Rounded.SystemUpdate),''', rel + ': enum')
s = once(s,
'''                SettingsSection.SAFETY -> SafetyPage(model, settings.uiStyle)\n                SettingsSection.UPDATE -> UpdatePage(model)''',
'''                SettingsSection.SAFETY -> SafetyPage(model, settings.uiStyle)\n                SettingsSection.BACKUP -> pageList { item { FullBackupCard(settings, actions) } }\n                SettingsSection.UPDATE -> UpdatePage(model)''', rel + ': when')
s = s.replace('model::setUpdateChannel', 'model::selectUpdateChannel')
write(rel, s)

# 3. Preset store gains an atomic replace operation for full-backup restore.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioPresetStore.kt'
s = read(rel)
s = once(s,
'''    suspend fun toggleFavorite(id: String) {\n        val now = System.currentTimeMillis()\n        mutate { current ->\n            current.map { item ->\n                if (item.id == id) item.copy(favorite = !item.favorite, updatedAt = now) else item\n            }\n        }\n    }\n\n    private suspend fun mutate''',
'''    suspend fun toggleFavorite(id: String) {\n        val now = System.currentTimeMillis()\n        mutate { current ->\n            current.map { item ->\n                if (item.id == id) item.copy(favorite = !item.favorite, updatedAt = now) else item\n            }\n        }\n    }\n\n    suspend fun replaceAll(items: List<StoredStudioPreset>) {\n        context.studioPresetDataStore.edit { preferences ->\n            preferences[studioPresetsKey] = encodePresets(\n                items.distinctBy { it.id }.sortedWith(presetOrder).take(STUDIO_PRESET_MAX_ITEMS),\n            )\n        }\n    }\n\n    private suspend fun mutate''', rel)
write(rel, s)

# 4. Direct switches are recorded only after the guarded task reports success.
rel = 'common/font_switch_task.sh'
s = read(rel)
s = once(s, 'STATUS_SCRIPT="$MODDIR/common/module_status.sh"\n', 'STATUS_SCRIPT="$MODDIR/common/module_status.sh"\nHISTORY_TOOL="$MODDIR/system/bin/luoshu-history"\n', rel + ': var')
s = once(s,
'''        write_task "$_task" success "$_font" '字体已准备完成；完整重启后自动验证实际加载状态' "$_started" "$_finished" ''\n''',
'''        write_task "$_task" success "$_font" '字体已准备完成；完整重启后自动验证实际加载状态' "$_started" "$_finished" ''\n        [ -f "$HISTORY_TOOL" ] && MODDIR="$MODDIR" sh "$HISTORY_TOOL" record-direct "$_font" >/dev/null 2>&1 || true\n''', rel + ': success')
write(rel, s)

# 5. Studio route: successful mix snapshots + history UI + richer glyph map callback.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/FontStudioRoute.kt'
s = read(rel)
s = once(s, '    var showGlyphBrowser by remember { mutableStateOf(false) }\n', '    var showGlyphBrowser by remember { mutableStateOf(false) }\n    var showSwitchHistory by remember { mutableStateOf(false) }\n', rel + ': state')
s = once(s,
'''    val studioTools: @Composable () -> Unit = {''',
'''    LaunchedEffect(state.taskState) {\n        if (state.taskState == "success") recordSuccessfulMixHistory()\n    }\n\n    val studioTools: @Composable () -> Unit = {''', rel + ': success recorder')
s = once(s,
'''            onPresets = { showPresetLibrary = true },\n            onProfile = { showProfileTransfer = true },''',
'''            onPresets = { showPresetLibrary = true },\n            onHistory = { showSwitchHistory = true },\n            onProfile = { showProfileTransfer = true },''', rel + ': tool callback')
s = once(s,
'''        StudioGlyphBrowserDialog(\n            style = style,\n            state = state,\n            onDismiss = { showGlyphBrowser = false },\n        )''',
'''        StudioGlyphBrowserDialog(\n            style = style,\n            state = state,\n            onInspectCoverage = stableActions.inspectCoverage,\n            onDismiss = { showGlyphBrowser = false },\n        )''', rel + ': coverage callback')
s = once(s,
'''    if (restoreNotice.isNotBlank()) {''',
'''    if (showSwitchHistory) {\n        SwitchHistoryDialog(style = style, onDismiss = { showSwitchHistory = false })\n    }\n    if (restoreNotice.isNotBlank()) {''', rel + ': dialog')
write(rel, s)

# 6. Tool launcher: distinguish saved presets from real successful switch history.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioToolLauncher.kt'
s = read(rel)
s = once(s, '    onPresets: () -> Unit,\n    onProfile: () -> Unit,', '    onPresets: () -> Unit,\n    onHistory: () -> Unit,\n    onProfile: () -> Unit,', rel + ': signature')
s = once(s,
'''                    StudioToolMenuItem(\n                        label = "方案导入导出",''',
'''                    StudioToolMenuItem(\n                        label = "成功切换历史",\n                        description = "最近 10 次真正完成的切换，可一键恢复并重新走安全事务",\n                        icon = Icons.Rounded.History,\n                        onClick = {\n                            menuVisible = false\n                            onHistory()\n                        },\n                    )\n                    StudioToolMenuItem(\n                        label = "方案导入导出",''', rel + ': item')
write(rel, s)

# 7. Coverage model: keep legacy fields, add rich map groups and recommendation.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/Alpha15FeatureViewModel.kt'
s = read(rel)
s = once(s,
'''internal data class CoverageMetrics(\n    val glyphs: Int = 0,''',
'''internal data class CoverageGroupMetrics(\n    val present: Int = 0,\n    val total: Int = 0,\n    val percent: Float = 0f,\n)\n\ninternal data class CoverageMetrics(\n    val glyphs: Int = 0,''', rel + ': group type')
s = once(s,
'''    val punctuationTotal: Int = 0,\n    val missingSample: String = "",\n) {''',
'''    val punctuationTotal: Int = 0,\n    val missingSample: String = "",\n    val groups: Map<String, CoverageGroupMetrics> = emptyMap(),\n    val missingByGroup: Map<String, String> = emptyMap(),\n    val recommendation: String = "",\n) {''', rel + ': fields')
old='''                        punctuationPresent = data.optJSONObject("punctuation")?.optInt("present", 0) ?: 0,\n                        punctuationTotal = data.optJSONObject("punctuation")?.optInt("total", 0) ?: 0,\n                        missingSample = data.optString("missingSample", ""),\n                    ),'''
new='''                        punctuationPresent = data.optJSONObject("punctuation")?.optInt("present", 0) ?: 0,\n                        punctuationTotal = data.optJSONObject("punctuation")?.optInt("total", 0) ?: 0,\n                        missingSample = data.optString("missingSample", ""),\n                        groups = parseCoverageGroups(data.optJSONObject("groups")),\n                        missingByGroup = parseMissingGroups(data.optJSONObject("missingByGroup")),\n                        recommendation = data.optString("recommendation", ""),\n                    ),'''
s = once(s, old, new, rel + ': parse')
s = once(s,
'''    private fun snapWeight(value: Int, min: Int, max: Int, step: Int): Int {''',
'''    private fun parseCoverageGroups(root: JSONObject?): Map<String, CoverageGroupMetrics> {\n        if (root == null) return emptyMap()\n        return buildMap {\n            val keys = root.keys()\n            while (keys.hasNext()) {\n                val key = keys.next()\n                val item = root.optJSONObject(key) ?: continue\n                put(\n                    key,\n                    CoverageGroupMetrics(\n                        present = item.optInt("present", 0),\n                        total = item.optInt("total", 0),\n                        percent = item.optDouble("percent", 0.0).toFloat().coerceIn(0f, 100f),\n                    ),\n                )\n            }\n        }\n    }\n\n    private fun parseMissingGroups(root: JSONObject?): Map<String, String> {\n        if (root == null) return emptyMap()\n        return buildMap {\n            val keys = root.keys()\n            while (keys.hasNext()) {\n                val key = keys.next()\n                root.optString(key).takeIf { it.isNotBlank() }?.let { put(key, it) }\n            }\n        }\n    }\n\n    private fun snapWeight(value: Int, min: Int, max: Int, step: Int): Int {''', rel + ': helpers')
write(rel, s)

# 8. Glyph browser now exposes the coverage map and can trigger detection for the selected slot.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioGlyphBrowser.kt'
s = read(rel)
s = once(s,
'''internal fun StudioGlyphBrowserDialog(\n    style: UiStyle,\n    state: FontStudioUiState,\n    onDismiss: () -> Unit,''',
'''internal fun StudioGlyphBrowserDialog(\n    style: UiStyle,\n    state: FontStudioUiState,\n    onInspectCoverage: (String) -> Unit,\n    onDismiss: () -> Unit,''', rel + ': signature')
s = once(s,
'''                    item {\n                        Row(\n                            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),''',
'''                    item {\n                        CoverageMapPanel(\n                            coverage = state.coverage,\n                            fontId = slotState?.font?.id.orEmpty(),\n                            fontName = slotState?.font?.name.orEmpty(),\n                            onInspect = onInspectCoverage,\n                        )\n                    }\n                    item {\n                        Row(\n                            modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),''', rel + ': panel')
write(rel, s)

# 9. Expand the actually-used compact A/B preview without changing the older dialog.
rel = 'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/StudioCompositePreviewCompact.kt'
s = read(rel)
s = once(s, 'import androidx.compose.foundation.layout.Arrangement\n', 'import androidx.compose.foundation.horizontalScroll\nimport androidx.compose.foundation.layout.Arrangement\n', rel + ': scroll import')
s = once(s, 'import androidx.compose.foundation.lazy.items\n', 'import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.rememberScrollState\n', rel + ': scroll state import')
s = once(s,
'''import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens\n\n@Composable''',
'''import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens\n\nprivate enum class CompactPreviewScenario(val label: String) {\n    MIXED("混排"), BODY("正文"), WECHAT("微信"), PLAY("Play"), STATUS("状态栏"),\n    NUMBERS("金额"), SMALL("小字"), HEADLINE("标题"),\n}\n\n@Composable''', rel + ': enum')
s = s.replace('StudioPreviewScenario', 'CompactPreviewScenario')
s = once(s, '        modifier = Modifier.fillMaxWidth(),\n        horizontalArrangement = Arrangement.spacedBy(6.dp),', '        modifier = Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),\n        horizontalArrangement = Arrangement.spacedBy(6.dp),', rel + ': selector scroll')
s = once(s, '                modifier = Modifier.weight(1f),\n                shape = RoundedCornerShape(15.dp),', '                modifier = Modifier.width(66.dp),\n                shape = RoundedCornerShape(15.dp),', rel + ': selector width')
# Insert four new system cases before NUMBERS.
s = once(s,
'''                CompactPreviewScenario.NUMBERS -> {\n                    Text("本月用量", fontSize = 12.sp)''',
'''                CompactPreviewScenario.WECHAT -> {\n                    Text("公众号文章标题", fontSize = 20.sp, fontWeight = FontWeight.Bold)\n                    Text("正文排版：中文阅读与 English 混排 2026", fontSize = 14.sp, lineHeight = 20.sp)\n                }\n                CompactPreviewScenario.PLAY -> {\n                    Text("Google Play", fontSize = 19.sp, fontWeight = FontWeight.Bold)\n                    Text("应用与游戏 · Apps & games", fontSize = 13.sp)\n                    Text("4.8 ★  ·  12 MB", fontSize = 12.sp)\n                }\n                CompactPreviewScenario.STATUS -> {\n                    Text("09:41   5G   88%", fontSize = 15.sp, fontWeight = FontWeight.Bold)\n                    Text("状态栏数字、符号与紧凑字宽", fontSize = 11.sp)\n                }\n                CompactPreviewScenario.SMALL -> {\n                    Text("辅助说明 · Secondary text · 12:45", fontSize = 10.sp)\n                    Text("小字号仍应保持清晰、字腔不过度拥挤。", fontSize = 11.sp)\n                }\n                CompactPreviewScenario.HEADLINE -> {\n                    Text("洛书字体引擎", fontSize = 27.sp, fontWeight = FontWeight.Black)\n                    Text("LuoShu Typography 2026", fontSize = 16.sp, fontWeight = FontWeight.Bold)\n                }\n                CompactPreviewScenario.NUMBERS -> {\n                    Text("本月用量", fontSize = 12.sp)''', rel + ': system cases')
# Candidate cases before numbers.
s = once(s,
'''                CompactPreviewScenario.NUMBERS -> {\n                    NativeFontPreview(cjk.font, "本月用量",''',
'''                CompactPreviewScenario.WECHAT -> {\n                    NativeFontPreview(cjk.font, "公众号文章标题", cjk.axes, Modifier.fillMaxWidth().height(38.dp), 20f, maxLines = 1)\n                    NativeFontPreview(cjk.font, "正文排版：中文阅读与", cjk.axes, Modifier.fillMaxWidth().height(29.dp), 14f, maxLines = 1)\n                    NativeFontPreview(latin.font, "English 2026", latin.axes, Modifier.fillMaxWidth().height(29.dp), 14f, maxLines = 1)\n                }\n                CompactPreviewScenario.PLAY -> {\n                    NativeFontPreview(latin.font, "Google Play", latin.axes, Modifier.fillMaxWidth().height(36.dp), 19f, maxLines = 1)\n                    NativeFontPreview(cjk.font, "应用与游戏", cjk.axes, Modifier.fillMaxWidth().height(28.dp), 13f, maxLines = 1)\n                    NativeFontPreview(digit.font, "4.8 ★ · 12 MB", digit.axes, Modifier.fillMaxWidth().height(28.dp), 12f, maxLines = 1)\n                }\n                CompactPreviewScenario.STATUS -> {\n                    NativeFontPreview(digit.font, "09:41   5G   88%", digit.axes, Modifier.fillMaxWidth().height(34.dp), 15f, maxLines = 1)\n                    NativeFontPreview(cjk.font, "状态栏数字、符号与紧凑字宽", cjk.axes, Modifier.fillMaxWidth().height(26.dp), 11f, maxLines = 1)\n                }\n                CompactPreviewScenario.SMALL -> {\n                    NativeFontPreview(latin.font, "Secondary text · 12:45", latin.axes, Modifier.fillMaxWidth().height(25.dp), 10f, maxLines = 1)\n                    NativeFontPreview(cjk.font, "小字号仍应保持清晰、字腔不过度拥挤。", cjk.axes, Modifier.fillMaxWidth().height(26.dp), 11f, maxLines = 1)\n                }\n                CompactPreviewScenario.HEADLINE -> {\n                    NativeFontPreview(cjk.font, "洛书字体引擎", cjk.axes, Modifier.fillMaxWidth().height(48.dp), 27f, maxLines = 1)\n                    NativeFontPreview(latin.font, "LuoShu Typography 2026", latin.axes, Modifier.fillMaxWidth().height(34.dp), 16f, maxLines = 1)\n                }\n                CompactPreviewScenario.NUMBERS -> {\n                    NativeFontPreview(cjk.font, "本月用量",''', rel + ': candidate cases')
write(rel, s)

# 10. Copy new/complete files.
for rel in [
    'system/bin/luoshu-history',
    'system/bin/luoshu-backup',
    'common/font_coverage_info.py',
    'scripts/switch_history_test.sh',
    'scripts/full_backup_root_test.sh',
    '.github/workflows/v2.5-beta1-feature-checks.yml',
    'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/SwitchHistoryDialog.kt',
    'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/studio/CoverageMapPanel.kt',
    'android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/settings/FullBackupManager.kt',
]:
    copy(rel)

# Executable bits are relevant in a real checkout.
for rel in ['system/bin/luoshu-history','system/bin/luoshu-backup','scripts/switch_history_test.sh','scripts/full_backup_root_test.sh']:
    (REPO / rel).chmod(0o755)
print('Applied LuoShu v2.5.0 Beta 1 feature overlay successfully.')
