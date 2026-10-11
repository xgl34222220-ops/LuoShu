package io.github.xgl34222220.luoshu.ui.home

import androidx.compose.runtime.Immutable

/** Another root module that ships font files or font XML and may override LuoShu. */
@Immutable
data class ForeignFontModule(val id: String, val name: String) {
    val label: String
        get() = if (name.isBlank() || name == id) id else "$name（$id）"
}

/**
 * Parses the bridge fields written by common/foreign_font_modules.sh:
 * ids = "a,b", names = "a:Name A|b:Name B". Every id is kept even when its name is missing.
 */
internal fun parseForeignFontModules(ids: String, names: String): List<ForeignFontModule> {
    val nameById = names.split('|').mapNotNull { entry ->
        val separator = entry.indexOf(':')
        if (separator <= 0) null else entry.substring(0, separator).trim() to entry.substring(separator + 1).trim()
    }.toMap()
    return ids.split(',').map { it.trim() }.filter { it.isNotEmpty() }.distinct().map { id ->
        ForeignFontModule(id = id, name = nameById[id].orEmpty().ifBlank { id })
    }
}

internal fun foreignFontWarningTitle(count: Int): String = "检测到 $count 个其他字体模块，可能覆盖洛书效果"

internal fun foreignFontWarningHint(fontLoaderPresent: Boolean): String = buildString {
    append("请在 Root 管理器中停用这些模块后重启，避免字体文件或 XML 互相覆盖。")
    if (fontLoaderPresent) append("FontLoader 是伴随模块，不算冲突，可以保留。")
}
