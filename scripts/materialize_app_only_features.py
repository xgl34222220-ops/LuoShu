#!/usr/bin/env python3
from pathlib import Path
import re


def replace(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing anchor in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def regex_replace(path: str, pattern: str, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"expected one regex replacement in {path}, got {count}")
    target.write_text(updated, encoding="utf-8")


app = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuApp.kt"
replace(app, "import android.view.Gravity\n", "import android.view.Gravity\nimport androidx.activity.compose.rememberLauncherForActivityResult\nimport androidx.activity.result.contract.ActivityResultContracts\n")
replace(app, "import androidx.compose.material.icons.rounded.Description\n", "import androidx.compose.material.icons.rounded.Description\nimport androidx.compose.material.icons.rounded.FileUpload\n")
replace(app, "import androidx.compose.ui.graphics.vector.ImageVector\n", "import androidx.compose.ui.graphics.vector.ImageVector\nimport androidx.compose.ui.platform.LocalContext\n")
replace(
    app,
    "    var pickerSlot by remember { mutableStateOf<MixSlot?>(null) }\n\n",
    """    var pickerSlot by remember { mutableStateOf<MixSlot?>(null) }
    val context = LocalContext.current
    val importLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.OpenMultipleDocuments(),
    ) { uris ->
        viewModel.importFonts(context, uris)
    }

""",
)
replace(
    app,
    """                        onDelete = { pendingDelete = it },
                        onRestoreDefault = { restoreDefault = true },
                        modifier = Modifier.padding(padding),
""",
    """                        onDelete = { pendingDelete = it },
                        onRestoreDefault = { restoreDefault = true },
                        onImport = {
                            importLauncher.launch(
                                arrayOf(
                                    "font/ttf",
                                    "font/otf",
                                    "font/collection",
                                    "application/x-font-ttf",
                                    "application/x-font-opentype",
                                    "application/vnd.ms-opentype",
                                    "application/octet-stream",
                                ),
                            )
                        },
                        modifier = Modifier.padding(padding),
""",
)
replace(
    app,
    """                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    viewModel.updateMixWeight(slot, normalizedWeight(font, selectedWeight(viewModel.mixState, slot)))
                    pickerSlot = null
                },
""",
    """                onChoose = { font ->
                    viewModel.updateMixFont(slot, font.id)
                    if (!viewModel.mixWeightAuto(slot)) {
                        viewModel.updateMixWeight(slot, normalizedWeight(font, selectedWeight(viewModel.mixState, slot)))
                    }
                    pickerSlot = null
                },
""",
)
replace(
    app,
    """private fun LibraryPage(
    viewModel: LuoShuViewModel,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize()) {
        PageHeader("FONT LIBRARY", "字体库", "真实字体预览 · 懒加载", { viewModel.refreshFonts(force = true) })
""",
    """private fun LibraryPage(
    viewModel: LuoShuViewModel,
    onApply: (FontItem) -> Unit,
    onDelete: (FontItem) -> Unit,
    onRestoreDefault: () -> Unit,
    onImport: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(modifier.fillMaxSize()) {
        PageHeader("FONT LIBRARY", "字体库", "真实字体预览 · 懒加载", { viewModel.refreshFonts(force = true) })
        GlassSurface(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 2.dp), RoundedCornerShape(26.dp)) {
            Row(Modifier.fillMaxWidth().padding(16.dp), verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    modifier = Modifier.size(46.dp),
                    shape = RoundedCornerShape(16.dp),
                    color = MaterialTheme.colorScheme.primary.copy(alpha = 0.12f),
                ) {
                    Box(contentAlignment = Alignment.Center) {
                        Icon(Icons.Rounded.FileUpload, contentDescription = null, tint = MaterialTheme.colorScheme.primary)
                    }
                }
                Spacer(Modifier.width(12.dp))
                Column(Modifier.weight(1f)) {
                    Text("APP 专属导入", fontWeight = FontWeight.Black, fontSize = 15.sp)
                    Text("从系统文件选择器导入 TTF / OTF / TTC；可多选，同字体族会自动归组。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp, lineHeight = 15.sp)
                }
                Spacer(Modifier.width(10.dp))
                Button(
                    onClick = onImport,
                    enabled = !viewModel.operationBusy && !viewModel.mixState.busy,
                    shape = RoundedCornerShape(16.dp),
                ) { Text("选择字体") }
            }
        }
""",
)
replace(app, 'Text("请将字体放入 /sdcard/LuoShu/fonts/", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)', 'Text("点击上方“选择字体”导入，或手动放入 /sdcard/LuoShu/fonts/", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)')
replace(app, 'PageHeader("FONT MIX", "字体组合", "只有真实支持的字重能力才会显示", viewModel::refreshMixConfig)', 'PageHeader("FONT MIX", "字体组合", "APP 默认多字重 · 可手动固定单档", viewModel::refreshMixConfig)')
replace(app, '                        "可变字体显示连续字重滑块；静态多字重只显示真实存在的档位；单一字体固定字重，不再伪造滑块。",\n', '                        "默认使用 APP 专属多字重，自动生成 300 / 400 / 500 / 600 / 700 五档；需要固定粗细时再切换到手动字重。WebUI 不提供这些入口。",\n')
replace(
    app,
    '                CapabilityPill(font?.let(::capabilityLabel) ?: "未选择", accentFor(title))\n',
    """                CapabilityPill(
                    when {
                        font == null -> "未选择"
                        selectedAuto(state, slot) -> "默认多字重"
                        else -> capabilityLabel(font)
                    },
                    accentFor(title),
                )
""",
)
replace(
    app,
    """                WeightControl(
                    font = font,
                    value = weight,
                    enabled = !state.busy,
                    onValue = { viewModel.updateMixWeight(slot, it) },
                )
""",
    """                WeightControl(
                    font = font,
                    value = weight,
                    auto = selectedAuto(state, slot),
                    enabled = !state.busy,
                    onAuto = { viewModel.updateMixWeightAuto(slot, it) },
                    onValue = { viewModel.updateMixWeight(slot, it) },
                )
""",
)
weight_control = '''@Composable
private fun WeightModeChip(
    title: String,
    subtitle: String,
    selected: Boolean,
    enabled: Boolean,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Surface(
        modifier = modifier.clip(RoundedCornerShape(18.dp)).clickable(enabled = enabled, onClick = onClick),
        shape = RoundedCornerShape(18.dp),
        color = if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.14f) else MaterialTheme.colorScheme.surface.copy(alpha = 0.62f),
        border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary.copy(alpha = 0.52f) else MaterialTheme.colorScheme.outline.copy(alpha = 0.16f)),
    ) {
        Column(Modifier.padding(horizontal = 13.dp, vertical = 10.dp)) {
            Text(title, color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface, fontWeight = FontWeight.Black, fontSize = 12.sp)
            Text(subtitle, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 9.sp)
        }
    }
}

@Composable
private fun WeightControl(
    font: FontItem,
    value: Int,
    auto: Boolean,
    enabled: Boolean,
    onAuto: (Boolean) -> Unit,
    onValue: (Int) -> Unit,
) {
    val axisInfo = rememberWeightAxisInfo(font)
    Column {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            WeightModeChip("默认多字重", "300 · 400 · 500 · 600 · 700", auto, enabled, { onAuto(true) }, Modifier.weight(1f))
            WeightModeChip("手动字重", "固定为单一粗细", !auto, enabled, { onAuto(false) }, Modifier.weight(1f))
        }
        Spacer(Modifier.height(10.dp))
        if (auto) {
            Surface(
                modifier = Modifier.fillMaxWidth(),
                shape = RoundedCornerShape(20.dp),
                color = MaterialTheme.colorScheme.primary.copy(alpha = 0.08f),
                border = BorderStroke(1.dp, MaterialTheme.colorScheme.primary.copy(alpha = 0.18f)),
            ) {
                Row(Modifier.fillMaxWidth().padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("按系统字重自动适配", fontWeight = FontWeight.Black, fontSize = 12.sp)
                        Text(
                            when {
                                font.variable -> "读取真实 wght 轴并生成五个常用字重，系统会按文字样式自动选择。"
                                staticWeights(font).size >= 2 -> "按字体族真实静态文件就近匹配五个常用字重，不伪造不存在的轮廓。"
                                else -> "该字体只有一个真实字重；仍建立五档系统映射，但各档复用同一轮廓。"
                            },
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            fontSize = 10.sp,
                            lineHeight = 15.sp,
                        )
                    }
                    Spacer(Modifier.width(10.dp))
                    CapabilityPill("APP 专属", Color(0xFF4679F5))
                }
            }
        } else {
            when {
                font.variable && axisInfo.loading -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                        Spacer(Modifier.width(9.dp))
                        Text("正在读取真实字重轴…", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp)
                    }
                }
                font.variable && axisInfo.hasWeight -> {
                    val minimum = axisInfo.min.coerceAtMost(axisInfo.max)
                    val maximum = axisInfo.max.coerceAtLeast(axisInfo.min + 1)
                    val safeValue = value.coerceIn(minimum, maximum)
                    val stepCount = (((maximum - minimum) / 10) - 1).coerceAtLeast(0)
                    Column {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Text("可变字重 · wght", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            Spacer(Modifier.weight(1f))
                            Text(safeValue.toString(), color = MaterialTheme.colorScheme.primary, fontWeight = FontWeight.Black)
                        }
                        Slider(
                            value = safeValue.toFloat(),
                            onValueChange = { onValue((it / 10f).toInt() * 10) },
                            enabled = enabled,
                            valueRange = minimum.toFloat()..maximum.toFloat(),
                            steps = stepCount,
                        )
                        Text("真实范围 $minimum–$maximum；手动模式只生成当前选定字重。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                }
                font.variable -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("可变字体，但没有 wght 轴", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            Text(axisInfo.error.ifBlank { "该字体可能只有 wdth、opsz 等轴，不能手动调节真实字重。" }, color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                        }
                        CapabilityPill("固定字重", Color(0xFF8A6CE8))
                    }
                }
                staticWeights(font).size >= 2 -> {
                    Column {
                        Text("真实字重档位", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        Spacer(Modifier.height(9.dp))
                        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            staticWeights(font).forEach { option ->
                                val selected = option == value
                                Surface(
                                    modifier = Modifier.clip(RoundedCornerShape(999.dp)).clickable(enabled = enabled) { onValue(option) },
                                    shape = RoundedCornerShape(999.dp),
                                    color = if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surface.copy(alpha = 0.66f),
                                    border = BorderStroke(1.dp, if (selected) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.outline.copy(alpha = 0.18f)),
                                ) {
                                    Text(weightName(option), modifier = Modifier.padding(horizontal = 13.dp, vertical = 8.dp), color = if (selected) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurface, fontSize = 11.sp, fontWeight = FontWeight.Bold)
                                }
                            }
                        }
                        Spacer(Modifier.height(8.dp))
                        Text("手动模式只使用所选真实静态字重。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                    }
                }
                else -> {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text("固定字重", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                            Text("该字体没有可调轴，也没有其他静态字重文件。", color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 10.sp)
                        }
                        CapabilityPill(weightName(fixedWeight(font)), Color(0xFF8A6CE8))
                    }
                }
            }
        }
    }
}
'''
regex_replace(app, r"@Composable\nprivate fun WeightControl\(.*?\n}\n@Composable\nprivate fun FontPickerDialog", weight_control + "\n@Composable\nprivate fun FontPickerDialog")
replace(
    app,
    """private fun selectedWeight(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

""",
    """private fun selectedWeight(state: MixState, slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> state.cjkWeight
    MixSlot.Latin -> state.latinWeight
    MixSlot.Digit -> state.digitWeight
}

private fun selectedAuto(state: MixState, slot: MixSlot): Boolean = when (slot) {
    MixSlot.Cjk -> state.cjkAuto
    MixSlot.Latin -> state.latinAuto
    MixSlot.Digit -> state.digitAuto
}

""",
)

vm = "android-app/app/src/main/java/io/github/xgl34222220/luoshu/LuoShuViewModel.kt"
replace(vm, "package io.github.xgl34222220.luoshu\n\n", "package io.github.xgl34222220.luoshu\n\nimport android.content.Context\nimport android.net.Uri\n")
replace(
    vm,
    """    val cjkWeight: Int = 400,
    val latinWeight: Int = 400,
    val digitWeight: Int = 400,
    val enabled: Boolean = false,
""",
    """    val cjkWeight: Int = 400,
    val latinWeight: Int = 400,
    val digitWeight: Int = 400,
    val cjkAuto: Boolean = true,
    val latinAuto: Boolean = true,
    val digitAuto: Boolean = true,
    val enabled: Boolean = false,
""",
)
replace(
    vm,
    """                    cjkWeight = data.optInt("cjkWeight", mixState.cjkWeight).coerceIn(100, 900),
                    latinWeight = data.optInt("latinWeight", mixState.latinWeight).coerceIn(100, 900),
                    digitWeight = data.optInt("digitWeight", mixState.digitWeight).coerceIn(100, 900),
                    message = if (data.optBoolean("enabled", false)) "当前正在使用复合字体" else "可直接生成新的复合字体",
""",
    """                    cjkWeight = data.optInt("cjkWeight", mixState.cjkWeight).coerceIn(100, 900),
                    latinWeight = data.optInt("latinWeight", mixState.latinWeight).coerceIn(100, 900),
                    digitWeight = data.optInt("digitWeight", mixState.digitWeight).coerceIn(100, 900),
                    cjkAuto = data.optBoolean("cjkAuto", true),
                    latinAuto = data.optBoolean("latinAuto", true),
                    digitAuto = data.optBoolean("digitAuto", true),
                    message = if (data.optBoolean("enabled", false)) "当前正在使用复合字体" else "可直接生成新的复合字体",
""",
)
replace(
    vm,
    """    fun updateMixWeight(slot: MixSlot, weight: Int) {
        val safe = (weight / 10 * 10).coerceIn(100, 900)
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjkWeight = safe)
            MixSlot.Latin -> mixState.copy(latinWeight = safe)
            MixSlot.Digit -> mixState.copy(digitWeight = safe)
        }
    }

""",
    """    fun updateMixWeight(slot: MixSlot, weight: Int) {
        val safe = (weight / 10 * 10).coerceIn(100, 900)
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjkWeight = safe)
            MixSlot.Latin -> mixState.copy(latinWeight = safe)
            MixSlot.Digit -> mixState.copy(digitWeight = safe)
        }
    }

    fun mixWeightAuto(slot: MixSlot): Boolean = when (slot) {
        MixSlot.Cjk -> mixState.cjkAuto
        MixSlot.Latin -> mixState.latinAuto
        MixSlot.Digit -> mixState.digitAuto
    }

    fun updateMixWeightAuto(slot: MixSlot, auto: Boolean) {
        mixState = when (slot) {
            MixSlot.Cjk -> mixState.copy(cjkAuto = auto)
            MixSlot.Latin -> mixState.copy(latinAuto = auto)
            MixSlot.Digit -> mixState.copy(digitAuto = auto)
        }
    }

""",
)
replace(
    vm,
    """                    append(RootShell.quote("wght=${mixState.cjkWeight}")).append(' ')
                    append(RootShell.quote("wght=${mixState.latinWeight}")).append(' ')
                    append(RootShell.quote("wght=${mixState.digitWeight}"))
""",
    """                    append(RootShell.quote(if (mixState.cjkAuto) "auto" else "wght=${mixState.cjkWeight}")).append(' ')
                    append(RootShell.quote(if (mixState.latinAuto) "auto" else "wght=${mixState.latinWeight}")).append(' ')
                    append(RootShell.quote(if (mixState.digitAuto) "auto" else "wght=${mixState.digitWeight}"))
""",
)
import_method = '''    fun importFonts(context: Context, uris: List<Uri>) {
        if (operationBusy || mixState.busy) return
        val selected = uris.distinctBy(Uri::toString)
        if (selected.isEmpty()) return
        operationBusy = true
        operationMessage = "正在读取所选字体…"
        viewModelScope.launch {
            var staged = emptyList<StagedFontImport>()
            var refreshAfter = false
            try {
                staged = stageFontImports(context, selected)
                var imported = 0
                var duplicates = 0
                val failures = mutableListOf<String>()
                staged.forEachIndexed { index, item ->
                    operationMessage = "正在导入 ${index + 1}/${staged.size}：${item.displayName}"
                    try {
                        val result = RootShell.exec(
                            "sh ${RootShell.quote(bridge)} import ${RootShell.quote(item.file.absolutePath)} ${RootShell.quote(item.displayName)}",
                            timeoutMs = 45_000L,
                        )
                        if (result.code != 0) error(result.stderr.ifBlank { "导入失败" })
                        val root = firstJson(result.stdout)
                        if (root.optString("status") != "ok") error(root.optString("message", "导入失败"))
                        val data = root.optJSONObject("data")
                        if (data?.optBoolean("imported", true) == false) duplicates += 1 else imported += 1
                    } catch (error: Throwable) {
                        failures += "${item.displayName}：${error.message ?: "导入失败"}"
                    }
                }
                refreshAfter = imported > 0
                operationMessage = buildString {
                    append("字体导入完成：新增 $imported 个")
                    if (duplicates > 0) append("，跳过重复 $duplicates 个")
                    if (failures.isNotEmpty()) append("，失败 ${failures.size} 个（${failures.first()}）")
                }
            } catch (error: Throwable) {
                operationMessage = error.message ?: "字体导入失败"
            } finally {
                cleanupFontImports(staged)
                operationBusy = false
                if (refreshAfter) refreshFonts(force = true)
            }
        }
    }

'''
replace(vm, "    fun deleteFont(fontId: String) {\n", import_method + "    fun deleteFont(fontId: String) {\n")

bridge = "common/app_bridge.sh"
replace(bridge, 'MIX_ENGINE="$MODDIR/common/v142_weighted_mix.sh"\n', 'MIX_ENGINE="$MODDIR/common/v142_weighted_mix.sh"\nAPP_MULTI_ENGINE="$MODDIR/common/app_multiweight_mix.sh"\nAPP_MODE_CONF="$MODDIR/config/app_weight_mode.conf"\n')
replace(bridge, '[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"\n', '[ -f "$MODDIR/common/util_functions.sh" ] && . "$MODDIR/common/util_functions.sh"\n[ -f "$MODDIR/common/font_check.sh" ] && . "$MODDIR/common/font_check.sh"\n')
replace(
    bridge,
    '    _task_file="$MODDIR/config/v143_axes_task.conf"\n    [ -s "$_task_file" ] || _task_file="$MODDIR/config/mix_task.conf"\n',
    '''    _task_file=""
    _task_mtime=-1
    for _candidate in "$MODDIR/config/app_multiweight_task.conf" "$MODDIR/config/v143_axes_task.conf" "$MODDIR/config/mix_task.conf"; do
        [ -s "$_candidate" ] || continue
        _mtime=$(stat -c %Y "$_candidate" 2>/dev/null || echo 0)
        case "$_mtime" in ''|*[!0-9]*) _mtime=0 ;; esac
        if [ "$_mtime" -gt "$_task_mtime" ] 2>/dev/null; then _task_file="$_candidate"; _task_mtime="$_mtime"; fi
    done
''',
)
bridge_helpers = '''app_cache_path_allowed() {
    case "$1" in
        /data/user/0/io.github.xgl34222220.luoshu/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu/cache/font-import/*|\\
        /data/user/0/io.github.xgl34222220.luoshu.debug/cache/font-import/*|/data/data/io.github.xgl34222220.luoshu.debug/cache/font-import/*) return 0 ;;
        *) return 1 ;;
    esac
}

import_font() {
    _src="$1"
    _requested=$(printf '%s' "$2" | tr -d '\\r\\n')
    app_cache_path_allowed "$_src" || { printf '{"status":"error","message":"字体来源不是受信任的 App 私有缓存"}\\n'; return 1; }
    [ -f "$_src" ] || { printf '{"status":"error","message":"所选字体缓存不存在"}\\n'; return 1; }
    _name=$(basename "$_requested")
    [ -n "$_name" ] || _name=$(basename "$_src")
    case "$_name" in ''|.|..|*/*|*\\\\*) printf '{"status":"error","message":"字体文件名无效"}\\n'; return 1 ;; esac
    _ext=${_name##*.}
    case "$_ext" in ttf|TTF|otf|OTF|ttc|TTC) ;; *) printf '{"status":"error","message":"仅支持 TTF、OTF 或 TTC 字体"}\\n'; return 1 ;; esac
    _size=$(wc -c <"$_src" 2>/dev/null | tr -d '[:space:]')
    case "$_size" in ''|*[!0-9]*) _size=0 ;; esac
    [ "$_size" -ge 12 ] 2>/dev/null && [ "$_size" -le 134217728 ] 2>/dev/null || { printf '{"status":"error","message":"字体文件大小异常或超过 128 MB"}\\n'; return 1; }
    type ensure_public_storage >/dev/null 2>&1 && ensure_public_storage
    mkdir -p "$USER_FONTS_DIR" 2>/dev/null || { printf '{"status":"error","message":"无法创建用户字体目录"}\\n'; return 1; }
    _stem=${_name%.*}; _dest="$USER_FONTS_DIR/$_name"
    if [ -f "$_dest" ]; then
        if cmp -s "$_src" "$_dest" 2>/dev/null; then
            _family=$(detect_font_family "$_name")
            printf '{"status":"ok","data":{"imported":false,"duplicate":true,"file":"%s","family":"%s"}}\\n' "$(json_escape "$_name")" "$(json_escape "$_family")"
            return 0
        fi
        _index=2
        while [ -e "$_dest" ]; do
            _name="${_stem}-${_index}.${_ext}"; _dest="$USER_FONTS_DIR/$_name"; _index=$((_index + 1))
        done
    fi
    _tmp="$USER_FONTS_DIR/.app-import-$$-${_name}"
    rm -f "$_tmp" 2>/dev/null || true
    cp -f "$_src" "$_tmp" 2>/dev/null || { printf '{"status":"error","message":"无法复制字体到用户目录"}\\n'; return 1; }
    chmod 0644 "$_tmp" 2>/dev/null || true
    if type font_validate >/dev/null 2>&1 && ! font_validate "$_tmp" text; then
        _error=${FONT_CHECK_ERROR:-字体文件校验失败}
        rm -f "$_tmp" 2>/dev/null || true
        printf '{"status":"error","message":"%s"}\\n' "$(json_escape "$_error")"
        return 1
    fi
    mv -f "$_tmp" "$_dest" 2>/dev/null || { rm -f "$_tmp"; printf '{"status":"error","message":"无法提交字体文件"}\\n'; return 1; }
    chmod 0644 "$_dest" 2>/dev/null || true
    rm -f "$MODDIR/config/webui_font_list.json" "$MODDIR/config/webui_font_list.key" 2>/dev/null || true
    _family=$(detect_font_family "$_name")
    printf '{"status":"ok","data":{"imported":true,"duplicate":false,"file":"%s","family":"%s","size":%s}}\\n' "$(json_escape "$_name")" "$(json_escape "$_family")" "$_size"
}

spec_auto() { [ "$1" = auto ]; }
write_app_weight_mode() {
    _ca=false; spec_auto "$1" && _ca=true
    _la=false; spec_auto "$2" && _la=true
    _da=false; spec_auto "$3" && _da=true
    mkdir -p "${APP_MODE_CONF%/*}" 2>/dev/null || true
    _tmp="${APP_MODE_CONF}.tmp.$$"
    printf 'cjkAuto=%s\\nlatinAuto=%s\\ndigitAuto=%s\\n' "$_ca" "$_la" "$_da" >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$APP_MODE_CONF" 2>/dev/null
    chmod 0644 "$APP_MODE_CONF" 2>/dev/null || true
}

'''
replace(bridge, 'case "${1:-status}" in\n', bridge_helpers + 'case "${1:-status}" in\n')
replace(
    bridge,
    '''    delete)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action delete "${2:-}"
        ;;
    mix_config)
        mix_ready || exit 1
        sh "$MIX_ENGINE" config
        ;;
    mix_start)
        mix_ready || exit 1
        sh "$MIX_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "${5:-wght=400}" "${6:-wght=400}" "${7:-wght=400}"
        ;;
    mix_status)
        mix_ready || exit 1
        sh "$MIX_ENGINE" status "${2:-}"
        ;;
''',
    '''    delete)
        manager_ready || exit 1
        sh "$FONT_MANAGER" action delete "${2:-}"
        ;;
    import)
        import_font "${2:-}" "${3:-}"
        ;;
    mix_config)
        if [ -f "$APP_MULTI_ENGINE" ]; then sh "$APP_MULTI_ENGINE" config; else mix_ready || exit 1; sh "$MIX_ENGINE" config; fi
        ;;
    mix_start)
        _ca="${5:-auto}"; _la="${6:-auto}"; _da="${7:-auto}"
        write_app_weight_mode "$_ca" "$_la" "$_da"
        case "$_ca $_la $_da" in
            *auto*) [ -f "$APP_MULTI_ENGINE" ] || { printf '{"status":"error","message":"APP 多字重引擎不存在"}\\n'; exit 1; }; sh "$APP_MULTI_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "$_ca" "$_la" "$_da" ;;
            *) mix_ready || exit 1; sh "$MIX_ENGINE" start "${2:-}" "${3:-}" "${4:-}" "$_ca" "$_la" "$_da" ;;
        esac
        ;;
    mix_status)
        case "${2:-}" in appmw-*) [ -f "$APP_MULTI_ENGINE" ] || exit 1; sh "$APP_MULTI_ENGINE" status "${2:-}" ;; *) mix_ready || exit 1; sh "$MIX_ENGINE" status "${2:-}" ;; esac
        ;;
''',
)

manager = "common/font_manager.sh"
replace(manager, 'LUOSHU_PUBLIC_DIR="/sdcard/LuoShu"\n', 'LUOSHU_PUBLIC_DIR="${LUOSHU_PUBLIC_DIR:-/sdcard/LuoShu}"\n')
replace(
    manager,
    '''find_text_font_file() {
    _font_id="$1"
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \\
''',
    '''find_text_font_file() {
    _font_id="$1"
    if type get_weight_file >/dev/null 2>&1; then
        _regular=$(get_weight_file "$_font_id" regular)
        [ -f "$_regular" ] && { echo "$_regular"; return 0; }
    fi
    for _f in "$USER_FONTS_DIR"/*.ttf "$USER_FONTS_DIR"/*.otf "$USER_FONTS_DIR"/*.ttc \\
''',
)
replace(
    manager,
    '''    # 同步预览字体到 webroot/fonts/（供 WebUI 用相对路径加载，避免 file:// CORS 限制）
    sync_preview_fonts 2>/dev/null || true
''',
    '''    # App 私有临时字体族不得同步到 WebUI 预览目录。
    if [ "${LUOSHU_PRIVATE_LIBRARY:-0}" != 1 ]; then
        sync_preview_fonts 2>/dev/null || true
    fi
''',
)

adapters = "common/rom_adapters.sh"
replace(
    adapters,
    '''copy_as_generic() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    sys_count=0
    core_count=0
''',
    '''copy_as_generic() {
    src="$1"
    dest_dir="$2"
    mode="${3:-full}"
    font_family="${4:-}"
    sys_count=0
    core_count=0
    weight_count=0
''',
)
replace(
    adapters,
    '''    _log_step "  已覆盖 $core_count 个通用字体文件"
    [ "$bad_count" -gt 0 ] && _log_step "  ⚠ 其中 $bad_count 个校验异常，请检查源字体文件是否完整"
    return 0
}
''',
    '''    _log_step "  已覆盖 $core_count 个通用字体文件"
    [ "$bad_count" -gt 0 ] && _log_step "  ⚠ 其中 $bad_count 个校验异常，请检查源字体文件是否完整"

    if [ -n "$font_family" ] && type scan_family_weights >/dev/null 2>&1; then
        weights=$(scan_family_weights "$font_family")
        for w in $(echo "$weights" | tr ',' ' '); do
            [ "$w" = regular ] && continue
            w_file=$(get_weight_file "$font_family" "$w")
            [ -f "$w_file" ] || continue
            w_anchor=$(_font_anchor "$w_file" "$dest_dir" "$w") || continue
            case "$w" in
                thin) targets="Roboto-Thin.ttf" ;;
                light) targets="Roboto-Light.ttf" ;;
                medium) targets="Roboto-Medium.ttf GoogleSans-Medium.ttf GoogleSansText-Medium.ttf" ;;
                semibold) targets="Roboto-SemiBold.ttf" ;;
                bold) targets="Roboto-Bold.ttf DroidSans-Bold.ttf GoogleSans-Bold.ttf GoogleSansText-Bold.ttf" ;;
                black) targets="Roboto-Black.ttf" ;;
                *) targets="" ;;
            esac
            for dest_name in $targets; do
                _rom_exact_target_exists "$dest_name" || continue
                _font_alias "$w_anchor" "$dest_dir/$dest_name" && weight_count=$((weight_count + 1))
            done
        done
        [ "$weight_count" -gt 0 ] && _log_step "  已创建 $weight_count 个通用 Android 字重变体文件"
    fi
    return 0
}
''',
)
replace(adapters, '        copy_as_generic "$src" "$dest_dir" "$mode"\n', '        copy_as_generic "$src" "$dest_dir" "$mode" "$font_family"\n')

multi = "common/app_multiweight_mix.sh"
replace(multi, 'TASK_FILE="$CONFIG_DIR/app_multiweight_task.conf"\n', 'TASK_FILE="$CONFIG_DIR/app_multiweight_task.conf"\nAPP_MODE_CONF="$CONFIG_DIR/app_weight_mode.conf"\n')
replace(
    multi,
    '''    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null || return 1
    cp -f "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true
''',
    '''    } >"$_tmp" 2>/dev/null && mv -f "$_tmp" "$MIX_CONF" 2>/dev/null || return 1
    _cauto=false; is_auto "$_ca" && _cauto=true
    _lauto=false; is_auto "$_la" && _lauto=true
    _dauto=false; is_auto "$_da" && _dauto=true
    _mode_tmp="$APP_MODE_CONF.tmp.$$"
    printf 'cjkAuto=%s\\nlatinAuto=%s\\ndigitAuto=%s\\n' "$_cauto" "$_lauto" "$_dauto" >"$_mode_tmp" 2>/dev/null && mv -f "$_mode_tmp" "$APP_MODE_CONF" 2>/dev/null || return 1
    cp -f "$MIX_CONF" "$AXIS_CONF" 2>/dev/null || true
''',
)
replace(
    multi,
    '''    _cauto=false; is_auto "$_ca" && _cauto=true; _lauto=false; is_auto "$_la" && _lauto=true; _dauto=false; is_auto "$_da" && _dauto=true
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\\r\\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
''',
    '''    if [ -s "$APP_MODE_CONF" ]; then
        _cauto=$(read_value "$APP_MODE_CONF" cjkAuto); _lauto=$(read_value "$APP_MODE_CONF" latinAuto); _dauto=$(read_value "$APP_MODE_CONF" digitAuto)
    else
        _cauto=true; _lauto=true; _dauto=true
    fi
    case "$_cauto" in true|false) ;; *) _cauto=true ;; esac
    case "$_lauto" in true|false) ;; *) _lauto=true ;; esac
    case "$_dauto" in true|false) ;; *) _dauto=true ;; esac
    _active=$(head -n1 "$ACTIVE_CONF" 2>/dev/null | tr -d '\\r\\n'); _enabled=false; [ "$_active" = mix ] && _enabled=true
''',
)

Path(__file__).unlink()
