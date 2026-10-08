package io.github.xgl34222220.luoshu.ui.launch

import android.graphics.Canvas
import android.graphics.ColorFilter
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.RadialGradient
import android.graphics.Rect
import android.graphics.Shader
import android.graphics.drawable.Drawable
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlassPalette
import kotlin.math.max

/** Responsive diffuse light shared by the first App Window frame and the real App backdrop. */
class LuoShuGlassBackdropDrawable(
    private val dark: Boolean,
    private val pureBlack: Boolean = false,
) : Drawable() {
    private var layers = emptyList<Paint>()
    private var drawableAlpha = 255
    private var drawableFilter: ColorFilter? = null

    override fun onBoundsChange(bounds: Rect) {
        val width = bounds.width().toFloat()
        val height = bounds.height().toFloat()
        if (width <= 0f || height <= 0f) {
            layers = emptyList()
            return
        }
        val palette = LuoShuGlassPalette
        if (dark && pureBlack) {
            layers = listOf(Paint().apply {
                color = 0xFF000000.toInt()
                alpha = drawableAlpha
                colorFilter = drawableFilter
            })
            return
        }
        val base = if (dark) palette.DarkBackground else palette.LightBackground
        val extent = max(width, height * .58f)
        layers = listOf(
            paint(LinearGradient(
                0f, 0f, width, height,
                intArrayOf(base, blend(base, palette.PurpleGlow, .055f), blend(base, palette.CyanGlow, .075f), base),
                floatArrayOf(0f, .38f, .78f, 1f), Shader.TileMode.CLAMP,
            )),
            glow(width * .10f, height * .20f, extent * .86f, palette.BlueGlow, if (dark) 73 else 136),
            glow(width * .96f, height * .35f, extent * .82f, palette.PurpleGlow, if (dark) 65 else 122),
            glow(width * .08f, height * .82f, extent * .87f, palette.CyanGlow, if (dark) 54 else 111),
            glow(width * .92f, height * .98f, extent * .72f, palette.BlueGlow, if (dark) 49 else 80),
            paint(LinearGradient(
                0f, height * .08f, width, height * .70f,
                intArrayOf(alpha(0xFFFFFFFF.toInt(), if (dark) 3 else 40), 0x00FFFFFF, alpha(0xFFFFFFFF.toInt(), if (dark) 5 else 32)),
                floatArrayOf(0f, .55f, 1f), Shader.TileMode.CLAMP,
            )),
        )
    }

    override fun draw(canvas: Canvas) {
        if (layers.isEmpty()) return
        val saved = canvas.save()
        canvas.translate(bounds.left.toFloat(), bounds.top.toFloat())
        layers.forEach { layer -> canvas.drawRect(0f, 0f, bounds.width().toFloat(), bounds.height().toFloat(), layer) }
        canvas.restoreToCount(saved)
    }

    override fun setAlpha(alpha: Int) {
        drawableAlpha = alpha.coerceIn(0, 255)
        layers.forEach { it.alpha = drawableAlpha }
        invalidateSelf()
    }

    override fun setColorFilter(colorFilter: ColorFilter?) {
        drawableFilter = colorFilter
        layers.forEach { it.colorFilter = colorFilter }
        invalidateSelf()
    }

    @Deprecated("Deprecated in Android")
    override fun getOpacity(): Int =
        if (drawableAlpha == 255 && drawableFilter == null) PixelFormat.OPAQUE
        else PixelFormat.TRANSLUCENT

    private fun paint(shader: Shader) = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG).apply {
        this.shader = shader
        alpha = drawableAlpha
        colorFilter = drawableFilter
    }

    private fun glow(x: Float, y: Float, radius: Float, color: Int, opacity: Int) = paint(
        RadialGradient(x, y, radius, intArrayOf(alpha(color, opacity), alpha(color, opacity / 3), alpha(color, 0)),
            floatArrayOf(0f, .52f, 1f), Shader.TileMode.CLAMP),
    )

    private fun alpha(color: Int, opacity: Int): Int = (color and 0x00FFFFFF) or (opacity shl 24)

    private fun blend(first: Int, second: Int, amount: Float): Int {
        fun channel(shift: Int): Int = ((((first ushr shift) and 255) * (1f - amount)) +
            (((second ushr shift) and 255) * amount)).toInt()
        return (255 shl 24) or (channel(16) shl 16) or (channel(8) shl 8) or channel(0)
    }
}
