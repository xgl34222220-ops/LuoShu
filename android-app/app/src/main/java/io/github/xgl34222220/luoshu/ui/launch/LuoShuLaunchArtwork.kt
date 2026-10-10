package io.github.xgl34222220.luoshu.ui.launch

import android.content.Context
import android.content.res.Configuration
import android.content.res.Resources
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.BitmapShader
import android.graphics.Canvas
import android.graphics.LinearGradient
import android.graphics.Matrix
import android.graphics.Paint
import android.graphics.Path
import android.graphics.RadialGradient
import android.graphics.RectF
import android.graphics.RenderEffect
import android.graphics.RenderNode
import android.graphics.Shader
import android.graphics.Typeface
import android.os.Build
import android.util.TypedValue
import androidx.annotation.RequiresApi
import io.github.xgl34222220.luoshu.R
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.cos
import kotlin.math.pow
import kotlin.math.sign
import kotlin.math.sin

/**
 * The single drawing of the launch shell: diffuse backdrop, frosted glass card with the
 * original icon tile, and the 洛书 wordmark. Both the API 31+ native preparation View and
 * the Compose launch shell call [draw], so their hand-off frames are pixel identical.
 *
 * Static parts (shadow, rim, highlight, icon tile) are pre-rendered by
 * design/launch/build_launch_assets.py; geometry constants here mirror that script.
 */
internal class LuoShuLaunchArtwork private constructor(
    resources: Resources,
    val dark: Boolean,
) {
    data class Frame(
        val drift: Float,
        val accent: Float,
        val cardScale: Float,
        /** -1 when no shimmer, otherwise 0..1 across the glass. */
        val shimmer: Float,
        val textAlpha: Float,
        val textRiseDp: Float,
    )

    private val density = resources.displayMetrics.density
    private val fontScale = resources.configuration.fontScale.coerceIn(.85f, 1.3f)
    private val backdrop = decode(resources, R.drawable.luoshu_launch_backdrop)
    private val backdropBlur = decode(resources, R.drawable.luoshu_launch_backdrop_blur)
    private val card = decode(resources, R.drawable.luoshu_launch_card)
    private val grain = decode(resources, R.drawable.luoshu_launch_grain)

    private val bitmapPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.FILTER_BITMAP_FLAG or Paint.DITHER_FLAG)
    private val grainPaint = Paint().apply {
        shader = BitmapShader(grain, Shader.TileMode.REPEAT, Shader.TileMode.REPEAT)
    }
    private val accentPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val shimmerPaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.DITHER_FLAG)
    private val titlePaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.SUBPIXEL_TEXT_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create("sans-serif", Typeface.BOLD)
        letterSpacing = .10f
        color = resources.getColor(R.color.launch_ink, null)
    }
    private val subtitlePaint = Paint(Paint.ANTI_ALIAS_FLAG or Paint.SUBPIXEL_TEXT_FLAG).apply {
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create("sans-serif-medium", Typeface.NORMAL)
        letterSpacing = .06f
        color = resources.getColor(R.color.launch_ink_secondary, null)
    }
    private val matrix = Matrix()
    private val blurMatrix = Matrix()
    private val cardRect = RectF()
    private val path = Path()
    private var pathEdge = -1f
    private var pathCenterX = 0f
    private var pathCenterY = 0f
    private var accentWidth = -1
    private var accentHeight = -1
    private var accents = emptyList<Accent>()
    private var blurNode: Any? = null

    init {
        titlePaint.textSize = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, TITLE_SP * fontScale, resources.displayMetrics)
        subtitlePaint.textSize = TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, SUBTITLE_SP * fontScale, resources.displayMetrics)
    }

    fun draw(canvas: Canvas, width: Int, height: Int, frame: Frame) {
        if (width <= 0 || height <= 0) return
        val w = width.toFloat()
        val h = height.toFloat()
        drawField(canvas, w, h, frame, withGrain = true)

        val cx = w / 2f
        val cy = h / 2f
        val edge = CARD_DP * density * frame.cardScale
        updatePath(cx, cy, edge)
        cardRect.set(cx - edge / 2f, cy - edge / 2f, cx + edge / 2f, cy + edge / 2f)

        // Frosted interior: what is behind, blurred. RenderEffect where the canvas supports it,
        // otherwise the pre-blurred bitmap of the same field (identical on a soft backdrop).
        val save = canvas.save()
        canvas.clipPath(path)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && canvas.isHardwareAccelerated) {
            drawBlurredInterior(canvas, w, h, frame)
        } else {
            fieldMatrix(blurMatrix, backdropBlur, w, h, frame.drift)
            canvas.drawBitmap(backdropBlur, blurMatrix, bitmapPaint)
            drawAccents(canvas, w, h, frame)
        }
        canvas.restoreToCount(save)

        val canvasEdge = CARD_CANVAS_DP * density * frame.cardScale
        cardRect.set(cx - canvasEdge / 2f, cy - canvasEdge / 2f, cx + canvasEdge / 2f, cy + canvasEdge / 2f)
        canvas.drawBitmap(card, null, cardRect, bitmapPaint)

        if (frame.shimmer in 0f..1f) drawShimmer(canvas, cx, cy, edge, frame.shimmer)

        if (frame.textAlpha > 0f) {
            val rise = frame.textRiseDp * density
            val titleBaseline = cy + CARD_DP * density / 2f + TITLE_GAP_DP * density + rise
            titlePaint.alpha = (255 * frame.textAlpha).toInt().coerceIn(0, 255)
            subtitlePaint.alpha = (235 * frame.textAlpha).toInt().coerceIn(0, 255)
            canvas.drawText(TITLE, cx, titleBaseline, titlePaint)
            canvas.drawText(SUBTITLE, cx, titleBaseline + SUBTITLE_GAP_DP * density * fontScale, subtitlePaint)
        }
    }

    private fun drawField(canvas: Canvas, w: Float, h: Float, frame: Frame, withGrain: Boolean) {
        fieldMatrix(matrix, backdrop, w, h, frame.drift)
        canvas.drawBitmap(backdrop, matrix, bitmapPaint)
        drawAccents(canvas, w, h, frame)
        if (withGrain) canvas.drawRect(0f, 0f, w, h, grainPaint)
    }

    /** Slow drift of the whole colour field; the starting window draws drift = 0. */
    private fun fieldMatrix(target: Matrix, bitmap: Bitmap, w: Float, h: Float, drift: Float) {
        target.setScale(w / bitmap.width, h / bitmap.height)
        val zoom = 1f + DRIFT_ZOOM * drift
        target.postScale(zoom, zoom, w * .40f, h * .38f)
        target.postTranslate(-w * .012f * drift, h * .010f * drift)
    }

    private fun drawAccents(canvas: Canvas, w: Float, h: Float, frame: Frame) {
        if (frame.accent <= 0f) return
        if (accentWidth != w.toInt() || accentHeight != h.toInt()) {
            accentWidth = w.toInt()
            accentHeight = h.toInt()
            accents = accentSpecs(dark).map { spec ->
                Accent(spec, RadialGradient(0f, 0f, spec.radius * w,
                    intArrayOf(spec.color, spec.color and 0x00FFFFFF), floatArrayOf(0f, 1f), Shader.TileMode.CLAMP))
            }
        }
        val phase = (frame.drift * PI).toFloat()
        for (accent in accents) {
            val spec = accent.spec
            val x = (spec.x + spec.dx * sin(phase)) * w
            val y = (spec.y + spec.dy * (1f - cos(phase)) / 2f) * h
            accentPaint.shader = accent.shader
            accentPaint.alpha = (255 * spec.alpha * frame.accent).toInt().coerceIn(0, 255)
            val save = canvas.save()
            canvas.translate(x, y)
            canvas.drawCircle(0f, 0f, spec.radius * w, accentPaint)
            canvas.restoreToCount(save)
        }
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun drawBlurredInterior(canvas: Canvas, w: Float, h: Float, frame: Frame) {
        val node = (blurNode as? RenderNode) ?: RenderNode("LuoShuLaunchGlass").also { blurNode = it }
        val pad = BLUR_DP * density * 2f
        val left = (cardRect.left - pad).coerceAtLeast(0f)
        val top = (cardRect.top - pad).coerceAtLeast(0f)
        val right = (cardRect.right + pad).coerceAtMost(w)
        val bottom = (cardRect.bottom + pad).coerceAtMost(h)
        node.setPosition(left.toInt(), top.toInt(), right.toInt(), bottom.toInt())
        val recording = node.beginRecording()
        try {
            recording.translate(-left.toInt().toFloat(), -top.toInt().toFloat())
            drawField(recording, w, h, frame, withGrain = true)
        } finally {
            node.endRecording()
        }
        val radius = BLUR_DP * density
        node.setRenderEffect(RenderEffect.createBlurEffect(radius, radius, Shader.TileMode.CLAMP))
        canvas.drawRenderNode(node)
    }

    private fun drawShimmer(canvas: Canvas, cx: Float, cy: Float, edge: Float, progress: Float) {
        val band = edge * .22f
        val peak = if (dark) 0x48FFFFFF else 0x8CFFFFFF.toInt()
        val gradient = LinearGradient(-band, 0f, band, 0f,
            intArrayOf(0x00FFFFFF, peak, 0x00FFFFFF), floatArrayOf(0f, .5f, 1f), Shader.TileMode.CLAMP)
        val local = Matrix()
        local.setRotate(SHIMMER_ANGLE)
        local.postTranslate(cx - edge * .9f + edge * 1.8f * progress, cy)
        gradient.setLocalMatrix(local)
        shimmerPaint.shader = gradient
        val save = canvas.save()
        canvas.clipPath(path)
        canvas.drawRect(cx - edge / 2f, cy - edge / 2f, cx + edge / 2f, cy + edge / 2f, shimmerPaint)
        canvas.restoreToCount(save)
    }

    /** Superellipse matching build_launch_assets.squircle_mask. */
    private fun updatePath(cx: Float, cy: Float, edge: Float) {
        if (edge == pathEdge && cx == pathCenterX && cy == pathCenterY) return
        pathEdge = edge
        pathCenterX = cx
        pathCenterY = cy
        path.reset()
        val a = edge / 2f
        val exponent = 2.0 / SQUIRCLE_N
        for (index in 0 until SQUIRCLE_POINTS) {
            val theta = 2.0 * PI * index / SQUIRCLE_POINTS
            val c = cos(theta)
            val s = sin(theta)
            val x = cx + a * (sign(c) * abs(c).pow(exponent)).toFloat()
            val y = cy + a * (sign(s) * abs(s).pow(exponent)).toFloat()
            if (index == 0) path.moveTo(x, y) else path.lineTo(x, y)
        }
        path.close()
    }

    private class AccentSpec(
        val x: Float, val y: Float, val dx: Float, val dy: Float,
        val radius: Float, val color: Int, val alpha: Float,
    )

    private class Accent(val spec: AccentSpec, val shader: Shader)

    companion object {
        const val CARD_DP = 208f
        const val CARD_CANVAS_DP = 288f
        const val CARD_START_SCALE = .955f
        private const val SQUIRCLE_N = 4.2
        private const val SQUIRCLE_POINTS = 192
        private const val BLUR_DP = 22f
        private const val DRIFT_ZOOM = .035f
        private const val SHIMMER_ANGLE = 20f
        private const val TITLE = "洛书"
        private const val SUBTITLE = "LuoShu · 字体管理"
        private const val TITLE_SP = 32f
        private const val SUBTITLE_SP = 13f
        private const val TITLE_GAP_DP = 58f
        private const val SUBTITLE_GAP_DP = 28f

        @Volatile private var cached: LuoShuLaunchArtwork? = null

        fun isDark(context: Context): Boolean =
            context.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES

        /** Shared by the native preparation View and the Compose shell: decode once per launch. */
        fun obtain(context: Context): LuoShuLaunchArtwork {
            val dark = isDark(context)
            cached?.takeIf { it.dark == dark && it.density == context.resources.displayMetrics.density }?.let { return it }
            return LuoShuLaunchArtwork(context.resources, dark).also { cached = it }
        }

        /** The launch is one-shot; drop the bitmaps once the shell has left the composition. */
        fun release() {
            cached = null
        }

        private fun decode(resources: Resources, id: Int): Bitmap =
            BitmapFactory.decodeResource(resources, id, BitmapFactory.Options().apply { inScaled = false })
                ?: error("Launch artwork resource $id could not be decoded")

        private fun accentSpecs(dark: Boolean): List<AccentSpec> = if (dark) {
            listOf(
                AccentSpec(.82f, .66f, -.05f, -.05f, .58f, 0xFF6C3080.toInt(), .30f),
                AccentSpec(.16f, .40f, .05f, .04f, .52f, 0xFF146478.toInt(), .28f),
            )
        } else {
            listOf(
                AccentSpec(.82f, .66f, -.05f, -.05f, .58f, 0xFFECC4E2.toInt(), .45f),
                AccentSpec(.16f, .40f, .05f, .04f, .52f, 0xFFA0DEE8.toInt(), .40f),
            )
        }
    }
}
