package io.github.xgl34222220.luoshu.ui.launch

import android.app.Activity
import android.content.res.Configuration
import android.graphics.drawable.ColorDrawable
import android.os.SystemClock
import android.util.Log
import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlassPalette

/** The real Window backdrop; Android owns the native splash and its default exit. */
internal class LuoShuLaunchController(private val activity: Activity) {
    private val exitPolicy = LuoShuLaunchExitPolicy()
    val isComplete: Boolean get() = exitPolicy.isComplete

    private var onComplete: (() -> Unit)? = null
    private var disposed = false
    private var contentDrawReported = false
    private var startedAt = 0L
    private var appearance: Triple<Boolean, Boolean, Boolean>? = null

    /** Install before setContent: the first App-controlled frame already has its backdrop. */
    fun install(startedAt: Long, onComplete: () -> Unit, nativeShell: Boolean = false) {
        this.startedAt = startedAt
        this.onComplete = onComplete
        val dark = activity.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
            Configuration.UI_MODE_NIGHT_YES
        if (nativeShell) {
            activity.window.setBackgroundDrawable(ColorDrawable(activity.getColor(io.github.xgl34222220.luoshu.R.color.launch_background)))
        } else {
            applyAppearance(dark, pureBlack = false)
        }
        // Keep the default platform exit. Registering a custom exit listener asks
        // Android to copy its splash into this Activity's decor. A delayed transfer
        // can then cover an already visible home frame, even if removal is immediate.
    }

    fun onContentDrawn() {
        if (contentDrawReported || disposed) return
        contentDrawReported = true
        event("content_draw_delivered")
        complete("content_drawn", exitPolicy.onContentDrawn())
    }

    fun stop() = complete("stop")

    fun finishForTaskEntry() = complete("task_entry")

    /** Preferences load asynchronously; never block the first frame on disk or Root work. */
    fun applyAppearance(dark: Boolean, pureBlack: Boolean, glassEnabled: Boolean = true) {
        val next = Triple(dark, pureBlack, glassEnabled)
        if (disposed || appearance == next) return
        appearance = next
        if (glassEnabled) {
            activity.window.setBackgroundDrawable(LuoShuGlassBackdropDrawable(dark, pureBlack))
        } else {
            val color = if (dark && pureBlack) 0xFF000000.toInt() else
                if (dark) LuoShuGlassPalette.DarkBackground else LuoShuGlassPalette.LightBackground
            activity.window.setBackgroundDrawable(ColorDrawable(color))
        }
    }

    fun dispose() {
        disposed = true
        onComplete = null
        complete("destroy")
    }

    private fun complete(reason: String, action: Action = exitPolicy.finish()) {
        if (action != Action.FINISH) return
        event("launch_complete", reason)
        val completion = onComplete
        onComplete = null
        if (!disposed) completion?.invoke()
    }

    private fun event(name: String, reason: String? = null) {
        val detail = if (reason == null) "" else " reason=$reason"
        Log.i("LuoShuStartup", "event=$name elapsedMs=${SystemClock.elapsedRealtime() - startedAt}$detail")
    }
}

