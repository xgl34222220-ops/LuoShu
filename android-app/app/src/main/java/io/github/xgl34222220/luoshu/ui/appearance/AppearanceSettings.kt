package io.github.xgl34222220.luoshu.ui.appearance

import androidx.compose.runtime.Immutable

enum class UiStyle(val label: String) {
    MATERIAL("Material"),
    MIUIX("Miuix");

    companion object {
        fun fromStorage(value: String?): UiStyle =
            entries.firstOrNull { it.name.equals(value, ignoreCase = true) } ?: MIUIX
    }
}

enum class ThemeMode(val storageValue: String, val label: String) {
    SYSTEM("system", "跟随系统"),
    LIGHT("light", "浅色"),
    DARK("dark", "深色");

    companion object {
        fun fromStorage(value: String?): ThemeMode =
            entries.firstOrNull { it.storageValue.equals(value, ignoreCase = true) } ?: SYSTEM
    }
}

enum class KolorStyle(val label: String) {
    SOFT("柔和"),
    VIBRANT("鲜艳"),
    NEUTRAL("中性");

    companion object {
        fun fromStorage(value: String?): KolorStyle = when (value?.lowercase()) {
            "neutral", "monochrome" -> NEUTRAL
            "vibrant", "expressive", "rainbow", "fruit_salad", "fidelity", "content" -> VIBRANT
            else -> SOFT
        }
    }
}

@Immutable
data class AccentOption(
    val id: String,
    val label: String,
    val argb: Int,
)

val AccentOptions = listOf(
    AccentOption("luoshu", "洛书蓝", 0xFF426FE8.toInt()),
    AccentOption("purple", "曜紫", 0xFF7857D8.toInt()),
    AccentOption("cyan", "青蓝", 0xFF0087A8.toInt()),
    AccentOption("green", "青玉", 0xFF16856B.toInt()),
    AccentOption("red", "朱红", 0xFFC43B43.toInt()),
    AccentOption("pink", "玫粉", 0xFFB83F78.toInt()),
)

fun accentOptionFor(argb: Int): AccentOption =
    AccentOptions.firstOrNull { it.argb == argb } ?: AccentOptions.first()

@Immutable
data class AppearanceSettings(
    val uiStyle: UiStyle = UiStyle.MIUIX,
    val themeMode: ThemeMode = ThemeMode.SYSTEM,
    val seedArgb: Int = AccentOptions.first().argb,
    val kolorStyle: KolorStyle = KolorStyle.VIBRANT,
    val monetEnabled: Boolean = true,
    val amoledBlack: Boolean = false,
    val blurEnabled: Boolean = true,
    val glassEnabled: Boolean = true,
    val floatingDock: Boolean = true,
) {
    val accent: AccentOption
        get() = accentOptionFor(seedArgb)
}
