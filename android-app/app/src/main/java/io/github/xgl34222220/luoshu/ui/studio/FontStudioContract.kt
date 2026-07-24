package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.runtime.Immutable
import io.github.xgl34222220.luoshu.Alpha15FeatureViewModel
import io.github.xgl34222220.luoshu.CoverageProbeState
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.LuoShuViewModel
import io.github.xgl34222220.luoshu.MixSlot
import io.github.xgl34222220.luoshu.ui.font.directApplyFontId
import io.github.xgl34222220.luoshu.ui.font.selectedAxes
import io.github.xgl34222220.luoshu.ui.font.selectedFontId
import io.github.xgl34222220.luoshu.ui.font.selectedWeight

@Immutable
internal data class StudioSlotUiState(
    val slot: MixSlot,
    val title: String,
    val subtitle: String,
    val sample: String,
    val font: FontItem? = null,
    val weight: Int = 400,
    val axes: Map<String, Float> = emptyMap(),
)

@Immutable
internal data class FontStudioUiState(
    val loading: Boolean = false,
    val operationBusy: Boolean = false,
    val busy: Boolean = false,
    val taskState: String = "idle",
    val message: String = "请选择中文、英文和数字字体",
    val progress: Int = 0,
    val error: String = "",
    val slots: List<StudioSlotUiState> = emptyList(),
    val fonts: List<FontItem> = emptyList(),
    val coverage: CoverageProbeState = CoverageProbeState(),
    val directApplyFontId: String? = null,
    val hasFonts: Boolean = false,
)

@Immutable
internal data class FontStudioActions(
    val refresh: () -> Unit,
    val pickSlot: (MixSlot) -> Unit,
    val updateFont: (MixSlot, String) -> Unit = { _, _ -> },
    val updateWeight: (MixSlot, Int) -> Unit,
    val updateAxis: (MixSlot, String, Float) -> Unit,
    val inspectCoverage: (String) -> Unit,
    val startMix: () -> Unit,
    val applyDirect: (String) -> Unit,
)

internal fun LuoShuViewModel.toFontStudioUiState(features: Alpha15FeatureViewModel): FontStudioUiState {
    val current = mixState
    fun slotState(
        slot: MixSlot,
        title: String,
        subtitle: String,
        sample: String,
    ): StudioSlotUiState {
        val fontId = selectedFontId(current, slot)
        return StudioSlotUiState(
            slot = slot,
            title = title,
            subtitle = subtitle,
            sample = sample,
            font = fonts.firstOrNull { it.id == fontId },
            weight = selectedWeight(current, slot),
            axes = selectedAxes(current, slot),
        )
    }

    return FontStudioUiState(
        loading = fontLoading || current.loading,
        operationBusy = operationBusy,
        busy = current.busy,
        taskState = current.taskState,
        message = current.message,
        progress = current.progress,
        error = current.error,
        slots = listOf(
            slotState(MixSlot.Cjk, "中文基底", "完整中文、符号与系统回退基底", "洛书中文 Aa 0123"),
            slotState(MixSlot.Latin, "英文字形", "替换拉丁字母与英文标点轮廓", "LuoShu Typography 0123"),
            slotState(MixSlot.Digit, "数字字形", "替换数字与相关半角标点", "0123456789 Aa"),
        ),
        fonts = fonts,
        coverage = features.coverage,
        directApplyFontId = directApplyFontId(current),
        hasFonts = fonts.isNotEmpty(),
    )
}
