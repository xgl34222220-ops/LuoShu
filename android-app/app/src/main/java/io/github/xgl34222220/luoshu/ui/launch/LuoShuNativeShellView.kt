package io.github.xgl34222220.luoshu.ui.launch

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.view.View
import io.github.xgl34222220.luoshu.R

/**
 * API 31+ preparation frame shown the moment the system splash exits: the static first
 * frame of the launch shell (same [LuoShuLaunchArtwork] drawing the Compose shell continues),
 * never home and never a copied splash icon. Noninteractive.
 */
internal class LuoShuNativeShellView(context: Context) : View(context) {
    private val artwork = LuoShuLaunchArtwork.obtain(context)
    private val firstFrame = LuoShuLaunchShellTimeline.first(textVisible = true)

    /** The same first frame rasterised off the main thread; see [LuoShuNativeShellGate]. */
    var prerendered: Bitmap? = null

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        contentDescription = "洛书"
        isClickable = false
        isFocusable = false
    }

    override fun onDraw(canvas: Canvas) {
        val ready = prerendered
        if (ready != null && ready.width == width && ready.height == height) {
            canvas.drawBitmap(ready, 0f, 0f, null)
        } else {
            artwork.draw(canvas, width, height, firstFrame)
        }
    }

    override fun onDetachedFromWindow() {
        super.onDetachedFromWindow()
        prerendered = null
    }

    companion object {
        /**
         * Background-thread raster of the first frame. A private artwork instance keeps
         * the shared one's paints and paths main-thread only.
         */
        fun prerender(context: Context, width: Int, height: Int): Bitmap {
            val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(context.getColor(R.color.launch_background))
            LuoShuLaunchArtwork.standalone(context)
                .draw(canvas, width, height, LuoShuLaunchShellTimeline.first(textVisible = true))
            // Hint RenderThread to upload now, before the first Window frame needs it.
            bitmap.prepareToDraw()
            return bitmap
        }
    }
}
