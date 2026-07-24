package io.github.xgl34222220.luoshu.ui.library

import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.RootShell
import org.json.JSONObject

private const val DETAILS_BRIDGE = "/data/adb/modules/LuoShu/common/font_details.sh"

internal data class FontDeepMetadata(
    val title: String,
    val text: String,
    val error: String = "",
)

internal suspend fun loadFontDeepMetadata(font: FontItem): FontDeepMetadata {
    return try {
        val result = RootShell.exec(
            "sh ${RootShell.quote(DETAILS_BRIDGE)} ${RootShell.quote(font.id)}",
            timeoutMs = 60_000L,
        )
        if (result.code != 0) error(result.stderr.ifBlank { "字体详情读取失败" })
        val root = firstMetadataJson(result.stdout)
        if (root.optString("status") != "ok") error(root.optString("message", "字体详情读取失败"))
        formatFontDeepMetadata(root.getJSONObject("data"), font.name)
    } catch (error: Throwable) {
        FontDeepMetadata(
            title = font.name,
            text = "",
            error = error.message ?: "字体详情读取失败",
        )
    }
}

internal fun formatFontDeepMetadata(data: JSONObject, fallbackName: String): FontDeepMetadata {
    val faces = data.getJSONArray("faces")
    val title = faces.optJSONObject(0)
        ?.optString("fullName", fallbackName)
        .orEmpty()
        .ifBlank { fallbackName }
    val text = buildString {
        append("文件：").append(data.optString("fileName", "未知")).append('\n')
        append("SHA-256：").append(data.optString("sha256", "未知")).append('\n')
        append("稳定文件 ID：").append(data.optString("fileUid", "未知")).append('\n')
        append("字体面数量：").append(data.optInt("faceCount", faces.length())).append('\n')
        append("文件大小：").append(formatMetadataBytes(data.optLong("bytes"))).append("\n\n")

        for (index in 0 until faces.length()) {
            val face = faces.optJSONObject(index) ?: continue
            val coverage = face.optJSONObject("coverage")
            val roles = coverage?.optJSONObject("roles")
            append("字体面 #").append(face.optInt("faceIndex", index)).append('\n')
            append("  名称：").append(face.optString("fullName", face.optString("family"))).append('\n')
            append("  Family：").append(face.optString("family", "未知")).append('\n')
            append("  Subfamily：").append(face.optString("subfamily", "未知")).append('\n')
            face.optString("postScriptName").takeIf { it.isNotBlank() }?.let {
                append("  PostScript：").append(it).append('\n')
            }
            append("  稳定 ID：").append(face.optString("uid", "未知")).append('\n')
            append("  格式：").append(face.optString("format", "未知"))
                .append(" · 字重 ").append(face.optInt("weight", 400))
                .append(if (face.optBoolean("italic")) " · 斜体" else " · 正体")
                .append('\n')
            append("  字形：").append(face.optInt("glyphs"))
                .append(" · Unicode：").append(coverage?.optInt("codepoints") ?: 0)
                .append(" · CJK：").append(coverage?.optInt("cjkCount") ?: 0)
                .append('\n')

            val roleLabels = buildList {
                if (roles?.optBoolean("cjk") == true) add("中文基底")
                if (roles?.optBoolean("latin") == true) add("英文")
                if (roles?.optBoolean("digit") == true) add("数字")
            }
            append("  推荐角色：")
                .append(if (roleLabels.isEmpty()) "不满足完整角色门禁" else roleLabels.joinToString("、"))
                .append('\n')

            val axes = face.optJSONArray("axes")
            if (axes != null && axes.length() > 0) {
                append("  可变轴：")
                for (axisIndex in 0 until axes.length()) {
                    val axis = axes.optJSONObject(axisIndex) ?: continue
                    if (axisIndex > 0) append("；")
                    append(axis.optString("tag"))
                        .append(' ')
                        .append(trimMetadataNumber(axis.optDouble("min")))
                        .append('–')
                        .append(trimMetadataNumber(axis.optDouble("max")))
                        .append("，默认 ")
                        .append(trimMetadataNumber(axis.optDouble("default")))
                }
                append('\n')
            } else {
                append("  可变轴：无\n")
            }
            if (index < faces.length() - 1) append('\n')
        }
    }.trimEnd()
    return FontDeepMetadata(title = title, text = text)
}

private fun firstMetadataJson(raw: String): JSONObject {
    val line = raw.lineSequence().firstOrNull { it.trimStart().startsWith("{") }
        ?: error("模块没有返回 JSON 数据")
    return JSONObject(line.trim())
}

private fun formatMetadataBytes(bytes: Long): String = when {
    bytes < 1024 -> "$bytes B"
    bytes < 1024 * 1024 -> "%.1f KB".format(bytes / 1024.0)
    else -> "%.1f MB".format(bytes / (1024.0 * 1024.0))
}

private fun trimMetadataNumber(value: Double): String {
    if (!value.isFinite()) return "0"
    val integer = value.toLong()
    return if (value == integer.toDouble()) integer.toString() else "%.2f".format(value).trimEnd('0').trimEnd('.')
}
