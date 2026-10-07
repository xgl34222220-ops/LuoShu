package io.github.xgl34222220.luoshu.ui.launch

import android.content.Context
import android.content.res.Configuration
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.Shader
import android.graphics.Typeface
import android.view.View
import androidx.core.content.ContextCompat
import io.github.xgl34222220.luoshu.R
import kotlin.math.min

/** First-frame artwork, with no input targets or accessibility nodes over the real App. */
internal class LuoShuLaunchArtView(context: Context) : View(context) {
    private var dark = resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
    private var pureBlack = false
    private var emblem = ContextCompat.getDrawable(context, R.drawable.ic_luoshu_launch)?.mutate()
    private val glass = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val rim = Paint(Paint.ANTI_ALIAS_FLAG).apply { style = Paint.Style.STROKE }
    private val sheen = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val bloom = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val title = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.DEFAULT_BOLD
        textAlign = Paint.Align.CENTER
        color = if (dark) 0xFFE5ECFA.toInt() else 0xFF304261.toInt()
    }
    private val caption = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        typeface = Typeface.DEFAULT
        textAlign = Paint.Align.CENTER
        color = if (dark) 0xFF9EACC8.toInt() else 0xFF667590.toInt()
    }
    private val card = RectF()
    private val sheenBounds = RectF()
    private val contour = Path()
    private var centerX = 0f
    private var centerY = 0f
    private var side = 0f

    init {
        background = LuoShuGlassBackdropDrawable(dark)
        isClickable = false
        isFocusable = false
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
    }

    /** Apply asynchronously available App preferences without delaying the first frame. */
    fun setAppearance(dark: Boolean, pureBlack: Boolean) {
        if (this.dark == dark && this.pureBlack == pureBlack) return
        this.dark = dark
        this.pureBlack = pureBlack
        background = LuoShuGlassBackdropDrawable(dark, pureBlack)
        val configuration = Configuration(resources.configuration).apply {
            uiMode = (uiMode and Configuration.UI_MODE_NIGHT_MASK.inv()) or
                if (dark) Configuration.UI_MODE_NIGHT_YES else Configuration.UI_MODE_NIGHT_NO
        }
        emblem = ContextCompat.getDrawable(context.createConfigurationContext(configuration), R.drawable.ic_luoshu_launch)?.mutate()
        title.color = if (dark) 0xFFE5ECFA.toInt() else 0xFF304261.toInt()
        caption.color = if (dark) 0xFF9EACC8.toInt() else 0xFF667590.toInt()
        if (width > 0 && height > 0) onSizeChanged(width, height, width, height)
        invalidate()
    }

    override fun onSizeChanged(width: Int, height: Int, oldWidth: Int, oldHeight: Int) {
        if (width <= 0 || height <= 0) {
            side = 0f
            return
        }
        val density = resources.displayMetrics.density
        val landscape = width > height
        side = min(min(width, height) * if (landscape) .32f else .45f, 192f * density)
        centerX = width * .5f
        // Keep the emblem on the native system splash axis to avoid a vertical jump.
        centerY = height * .5f
        card.set(centerX - side / 2f, centerY - side / 2f, centerX + side / 2f, centerY + side / 2f)
        sheenBounds.set(card.left - side * .16f, card.top - side * .42f, card.right + side * .15f, centerY + side * .02f)
        buildContour(card, side * .28f)
        glass.shader = LinearGradient(card.left, card.top, card.right, card.bottom,
            intArrayOf(if (dark) 0x26FFFFFF else 0xBBFFFFFF.toInt(), if (dark) 0x0BFFFFFF else 0x52FFFFFF,
                if (dark) 0x12FFFFFF else 0x85FFFFFF.toInt()), floatArrayOf(0f, .58f, 1f), Shader.TileMode.CLAMP)
        rim.shader = LinearGradient(card.left, card.top, card.right, card.bottom,
            intArrayOf(if (dark) 0x75FFFFFF else 0xEEFFFFFF.toInt(), if (dark) 0x08FFFFFF else 0x35FFFFFF,
                if (dark) 0x2FFFFFFF else 0xC5FFFFFF.toInt()), floatArrayOf(0f, .6f, 1f), Shader.TileMode.CLAMP)
        rim.strokeWidth = density * .8f
        bloom.shader = RadialGradient(centerX, centerY + side * .20f, side * .83f,
            intArrayOf(if (dark) 0x477094E8 else 0x28536B8E, 0x00000000), null, Shader.TileMode.CLAMP)
        sheen.shader = LinearGradient(card.left, card.top, centerX, card.bottom,
            intArrayOf(if (dark) 0x18FFFFFF else 0x58FFFFFF, 0x00FFFFFF), null, Shader.TileMode.CLAMP)
        title.textSize = min(27f * density, side * .17f)
        caption.textSize = min(12f * density, side * .083f)
        val iconSide = side * 1.48f
        emblem?.setBounds((centerX - iconSide / 2).toInt(), (centerY - iconSide / 2).toInt(),
            (centerX + iconSide / 2).toInt(), (centerY + iconSide / 2).toInt())
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)
        if (side <= 0f) return
        canvas.drawCircle(centerX, centerY + side * .20f, side * .83f, bloom)
        canvas.drawPath(contour, glass)
        val saved = canvas.save()
        canvas.clipPath(contour)
        canvas.drawOval(sheenBounds, sheen)
        canvas.restoreToCount(saved)
        canvas.drawPath(contour, rim)
        emblem?.draw(canvas)
        canvas.drawText("洛书", centerX, card.bottom + title.textSize * 1.72f, title)
        canvas.drawText("字里行间，自有风格。", centerX, card.bottom + title.textSize * 1.72f + caption.textSize * 2.1f, caption)
    }

    private fun buildContour(rect: RectF, radius: Float) {
        contour.reset()
        contour.moveTo(rect.left + radius, rect.top)
        contour.lineTo(rect.right - radius, rect.top)
        contour.cubicTo(rect.right - radius * .30f, rect.top, rect.right, rect.top + radius * .30f, rect.right, rect.top + radius)
        contour.lineTo(rect.right, rect.bottom - radius)
        contour.cubicTo(rect.right, rect.bottom - radius * .30f, rect.right - radius * .30f, rect.bottom, rect.right - radius, rect.bottom)
        contour.lineTo(rect.left + radius, rect.bottom)
        contour.cubicTo(rect.left + radius * .30f, rect.bottom, rect.left, rect.bottom - radius * .30f, rect.left, rect.bottom - radius)
        contour.lineTo(rect.left, rect.top + radius)
        contour.cubicTo(rect.left, rect.top + radius * .30f, rect.left + radius * .30f, rect.top, rect.left + radius, rect.top)
        contour.close()
    }
}
