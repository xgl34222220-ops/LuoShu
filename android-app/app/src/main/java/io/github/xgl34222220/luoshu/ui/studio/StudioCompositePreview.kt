package io.github.xgl34222220.luoshu.ui.studio

import io.github.xgl34222220.luoshu.MixSlot

internal data class StudioQuickPreset(
    val id: String,
    val label: String,
    val description: String,
    val cjkWeight: Int,
    val latinWeight: Int,
    val digitWeight: Int,
)

internal val studioQuickPresets = listOf(
    StudioQuickPreset("balanced", "均衡", "三种文字保持一致视觉重量", 400, 400, 400),
    StudioQuickPreset("reading", "正文", "中文与英文自然，数字稍加强", 400, 400, 500),
    StudioQuickPreset("headline", "标题", "适合标题、桌面和设置页", 600, 600, 600),
    StudioQuickPreset("numbers", "数字强化", "金额、时间和状态数字更醒目", 400, 400, 650),
)

internal fun StudioQuickPreset.weightFor(slot: MixSlot): Int = when (slot) {
    MixSlot.Cjk -> cjkWeight
    MixSlot.Latin -> latinWeight
    MixSlot.Digit -> digitWeight
}
