package io.github.xgl34222220.luoshu.ui.launch

import android.content.Context
import android.graphics.Canvas
import android.view.View

/**
 * API 31+ preparation frame shown the moment the system splash exits: the static first
 * frame of the launch shell (same [LuoShuLaunchArtwork] drawing the Compose shell continues),
 * never home and never a copied splash icon. Noninteractive.
 */
internal class LuoShuNativeShellView(context: Context) : View(context) {
    private val artwork = LuoShuLaunchArtwork.obtain(context)
    private val firstFrame = LuoShuLaunchShellTimeline.first(textVisible = true)

    init {
        importantForAccessibility = IMPORTANT_FOR_ACCESSIBILITY_YES
        contentDescription = "洛书"
        isClickable = false
        isFocusable = false
    }

    override fun onDraw(canvas: Canvas) {
        artwork.draw(canvas, width, height, firstFrame)
    }
}
