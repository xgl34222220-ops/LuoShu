package io.github.xgl34222220.luoshu.hook

import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.nio.charset.StandardCharsets
import org.junit.Assert.assertTrue
import org.junit.Test

class SfntFontIdentityTest {
    @Test
    fun readsGoogleSansTextFromOpaqueSfntBuffer() {
        val name = "Google Sans Text"
        val encoded = name.toByteArray(StandardCharsets.UTF_16BE)
        val nameTableOffset = 28
        val nameTableLength = 18 + encoded.size
        val buffer = ByteBuffer.allocate(nameTableOffset + nameTableLength).order(ByteOrder.BIG_ENDIAN)

        buffer.putInt(0x00010000)
        buffer.putShort(1.toShort())
        buffer.putShort(0.toShort())
        buffer.putShort(0.toShort())
        buffer.putShort(0.toShort())

        buffer.putInt(0x6E616D65)
        buffer.putInt(0)
        buffer.putInt(nameTableOffset)
        buffer.putInt(nameTableLength)

        buffer.position(nameTableOffset)
        buffer.putShort(0.toShort())
        buffer.putShort(1.toShort())
        buffer.putShort(18.toShort())
        buffer.putShort(3.toShort())
        buffer.putShort(1.toShort())
        buffer.putShort(0x0409.toShort())
        buffer.putShort(16.toShort())
        buffer.putShort(encoded.size.toShort())
        buffer.putShort(0.toShort())
        buffer.put(encoded)
        buffer.flip()

        val identity = SfntFontIdentity.fromBuffer(buffer).orEmpty()
        assertTrue(identity.contains("Google Sans Text"))
    }
}
