package io.github.xgl34222220.luoshu.ui.launch

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.max
import kotlin.math.min

/**
 * One-shot launch shell motion, pure math so it is unit tested without a device.
 * Elapsed time is the Compose clock, which already applies the system animator scale.
 * The shell is drawn above an already composed home, so this never gates readiness.
 */
internal object LuoShuLaunchShellTimeline {
    const val TOTAL_MS = 1350f
    const val EXIT_START_MS = 1000f
    const val EXIT_MS = TOTAL_MS - EXIT_START_MS
    const val CARD_SETTLE_MS = 520f
    const val SHIMMER_START_MS = 380f
    const val SHIMMER_END_MS = 980f
    const val TEXT_FADE_MS = 360f
    const val ACCENT_FADE_MS = 600f

    /** First frame: identical to the system splash hand-off and the API 28–30 starting window. */
    fun first(textVisible: Boolean) = frameAt(0f, textVisible)

    fun frameAt(elapsedMs: Float, textAlreadyVisible: Boolean): LuoShuLaunchArtwork.Frame {
        val t = elapsedMs.coerceIn(0f, TOTAL_MS)
        val settle = easeOut(t / CARD_SETTLE_MS)
        val exit = easeInOut((t - EXIT_START_MS) / EXIT_MS)
        val shimmer = if (t in SHIMMER_START_MS..SHIMMER_END_MS) {
            (t - SHIMMER_START_MS) / (SHIMMER_END_MS - SHIMMER_START_MS)
        } else {
            -1f
        }
        val text = if (textAlreadyVisible) 1f else easeOut(t / TEXT_FADE_MS)
        return LuoShuLaunchArtwork.Frame(
            drift = easeInOut(t / TOTAL_MS),
            accent = easeInOut(t / ACCENT_FADE_MS),
            cardScale = LuoShuLaunchArtwork.CARD_START_SCALE +
                (1f - LuoShuLaunchArtwork.CARD_START_SCALE) * settle + .025f * exit,
            shimmer = shimmer,
            textAlpha = text,
            textRiseDp = (1f - text) * 8f,
        )
    }

    /** Whole-shell opacity: opaque until the crossfade into the already drawn home. */
    fun shellAlpha(elapsedMs: Float): Float = 1f - easeInOut((elapsedMs - EXIT_START_MS) / EXIT_MS)

    private fun clamp(value: Float) = max(0f, min(1f, value))

    private fun easeOut(value: Float): Float {
        val x = clamp(value)
        val inverse = 1f - x
        return 1f - inverse * inverse * inverse
    }

    private fun easeInOut(value: Float): Float = (.5f - .5f * cos(PI * clamp(value))).toFloat()
}
