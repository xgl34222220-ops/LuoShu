package io.github.xgl34222220.luoshu.hook

import java.io.File
import java.io.FileInputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.Charset
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap

/** Reads only the SFNT name table so UUID-named Android downloaded fonts can be identified safely. */
internal object SfntFontIdentity {
    private const val TTC_TAG = 0x74746366
    private const val NAME_TAG = 0x6E616D65
    private const val MAX_NAME_RECORDS = 512
    private const val MAX_NAME_BYTES = 4096

    private val cache = ConcurrentHashMap<String, String>()

    fun fromFile(file: File?): String? {
        if (file == null || !file.isFile || !file.canRead()) return null
        val key = "${file.path}|${file.length()}|${file.lastModified()}"
        cache[key]?.let { return it.ifEmpty { null } }
        val value = runCatching {
            FileInputStream(file).channel.use { channel ->
                if (channel.size() <= 0L || channel.size() > Int.MAX_VALUE.toLong()) return@use null
                parse(channel.map(java.nio.channels.FileChannel.MapMode.READ_ONLY, 0L, channel.size()))
            }
        }.getOrNull()
        cache[key] = value.orEmpty()
        return value
    }

    fun fromBuffer(source: ByteBuffer?): String? {
        source ?: return null
        return runCatching { parse(source.duplicate()) }.getOrNull()
    }

    private fun parse(source: ByteBuffer): String? {
        val buffer = source.order(ByteOrder.BIG_ENDIAN)
        val base = buffer.position()
        if (!has(buffer, base, 12)) return null
        val sfntOffset = if (buffer.getInt(base) == TTC_TAG) {
            val count = unsignedInt(buffer.getInt(base + 8))
            if (count < 1L || count > 128L || !has(buffer, base + 12, 4)) return null
            buffer.getInt(base + 12)
        } else {
            base
        }
        if (!has(buffer, sfntOffset, 12)) return null
        val tableCount = unsignedShort(buffer.getShort(sfntOffset + 4)).coerceAtMost(512)
        val directory = sfntOffset + 12
        var nameOffset = -1
        var nameLength = 0
        repeat(tableCount) { index ->
            val record = directory + index * 16
            if (!has(buffer, record, 16)) return@repeat
            if (buffer.getInt(record) == NAME_TAG) {
                nameOffset = buffer.getInt(record + 8)
                nameLength = buffer.getInt(record + 12)
            }
        }
        if (nameOffset < 0 || nameLength <= 0 || !has(buffer, nameOffset, 6)) return null

        val count = unsignedShort(buffer.getShort(nameOffset + 2)).coerceAtMost(MAX_NAME_RECORDS)
        val strings = nameOffset + unsignedShort(buffer.getShort(nameOffset + 4))
        val names = linkedSetOf<String>()
        repeat(count) { index ->
            val record = nameOffset + 6 + index * 12
            if (!has(buffer, record, 12)) return@repeat
            val platform = unsignedShort(buffer.getShort(record))
            val nameId = unsignedShort(buffer.getShort(record + 6))
            if (nameId !in INTERESTING_NAME_IDS) return@repeat
            val length = unsignedShort(buffer.getShort(record + 8)).coerceAtMost(MAX_NAME_BYTES)
            val offset = unsignedShort(buffer.getShort(record + 10))
            val start = strings + offset
            if (length <= 0 || !has(buffer, start, length)) return@repeat
            val bytes = ByteArray(length)
            val copy = buffer.duplicate()
            copy.position(start)
            copy.get(bytes)
            decode(bytes, platform)
                ?.trim()
                ?.replace('\u0000', ' ')
                ?.replace(Regex("\\s+"), " ")
                ?.takeIf { it.length in 2..160 }
                ?.let(names::add)
        }
        return names.takeIf { it.isNotEmpty() }?.joinToString("|")
    }

    private fun decode(bytes: ByteArray, platform: Int): String? = runCatching {
        when (platform) {
            0, 3 -> String(bytes, StandardCharsets.UTF_16BE)
            1 -> String(bytes, runCatching { Charset.forName("x-MacRoman") }.getOrDefault(StandardCharsets.ISO_8859_1))
            else -> String(bytes, StandardCharsets.UTF_8)
        }
    }.getOrNull()

    private fun has(buffer: ByteBuffer, offset: Int, length: Int): Boolean =
        offset >= 0 && length >= 0 && offset <= buffer.limit() - length

    private fun unsignedShort(value: Short): Int = value.toInt() and 0xFFFF
    private fun unsignedInt(value: Int): Long = value.toLong() and 0xFFFFFFFFL

    private val INTERESTING_NAME_IDS = setOf(1, 2, 4, 6, 16, 17)
}
