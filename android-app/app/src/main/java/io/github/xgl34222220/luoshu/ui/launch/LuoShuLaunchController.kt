package io.github.xgl34222220.luoshu.ui.launch

import android.app.Activity
import android.content.res.Configuration
import android.graphics.drawable.ColorDrawable
import android.os.Build
import android.os.SystemClock
import android.util.Log
import androidx.annotation.RequiresApi
import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action
import io.github.xgl34222220.luoshu.ui.theme.LuoShuGlassPalette

/** The real Window backdrop and immediate system-splash cleanup; no second launch page. */
internal class LuoShuLaunchController(private val activity: Activity) {
    private val exitPolicy = LuoShuLaunchExitPolicy()
    val isComplete: Boolean get() = exitPolicy.isComplete

    private var onComplete: (() -> Unit)? = null
    private var disposed = false
    private var contentDrawReported = false
    private var startedAt = 0L
    private var appearance: Triple<Boolean, Boolean, Boolean>? = null

    /** Install before setContent: the first App-controlled frame already has its backdrop. */
    fun install(startedAt: Long, onComplete: () -> Unit) {
        this.startedAt = startedAt
        this.onComplete = onComplete
        val dark = activity.resources.configuration.uiMode and Configuration.UI_MODE_NIGHT_MASK ==
            Configuration.UI_MODE_NIGHT_YES
        applyAppearance(dark, pureBlack = false)
        // Register for every launch, including recreation, task entry and reduced motion.
        // There is no custom animation in any of those paths.
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) installPlatformExit()
    }

    fun onContentDrawn() {
        if (contentDrawReported || disposed) return
        contentDrawReported = true
        event("content_draw_delivered")
        complete("content_drawn", exitPolicy.onContentDrawn())
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun installPlatformExit() {
        activity.splashScreen.setOnExitAnimationListener { splash ->
            event("native_exit_received")
            // Never retain, animate or repost this view. Even a late callback after
            // stop/task entry must remove its system layer in this same callback.
            if (exitPolicy.onNativeExit() == Action.REMOVE_NATIVE) {
                splash.remove()
                event("native_removed")
            }
        }
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) clearPlatformExit()
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun clearPlatformExit() {
        activity.splashScreen.clearOnExitAnimationListener()
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
