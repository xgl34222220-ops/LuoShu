package io.github.xgl34222220.luoshu.ui.launch

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Activity
import android.os.Build
import android.os.SystemClock
import android.util.Log
import android.view.View
import android.view.ViewGroup
import android.view.animation.PathInterpolator
import androidx.annotation.RequiresApi
import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchExitPolicy.Action

/** Native exit followed by visible artwork; no input shield or dependency on root work. */
internal class LuoShuLaunchController(private val activity: Activity) {
    private val nativeExitRequired = Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
    private val exitPolicy = LuoShuLaunchExitPolicy(nativeExitRequired)
    val isComplete: Boolean get() = exitPolicy.isComplete

    private var activeView: View? = null
    private var removeActiveSplash: (() -> Unit)? = null
    private var onComplete: (() -> Unit)? = null
    private var completionDispatched = false
    private var disposed = false
    private var stopped = false
    private var artwork: LuoShuLaunchArtView? = null
    private var showArtwork = false
    private var contentDrawReported = false
    private var startedAt = 0L
    private var callbackView: View? = null
    private val startArtworkOnFrame = Runnable {
        perform(exitPolicy.onNextFrame(ValueAnimator.areAnimatorsEnabled()), "reduced_motion")
    }
    private val missingNativeExit = Runnable {
        perform(exitPolicy.onMissingNativeExit(), "native_exit_watchdog")
    }

    fun install(skipExitAnimation: Boolean, startedAt: Long, onComplete: () -> Unit) {
        this.startedAt = startedAt
        this.onComplete = onComplete
        showArtwork = !skipExitAnimation && ValueAnimator.areAnimatorsEnabled()
        perform(exitPolicy.onInstall(showArtwork), if (skipExitAnimation) "task_or_recreation" else "reduced_motion")
        if (!showArtwork) {
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) installPlatformExit()
    }

    /** Attach after setContent, above the App, with touch and a11y passing through. */
    fun attachArtwork() {
        if (!showArtwork || disposed || stopped || isComplete) return
        val decor = activity.window.decorView as? ViewGroup ?: run {
            completeArtwork("missing_decor")
            return
        }
        callbackView = decor
        artwork = LuoShuLaunchArtView(activity).also {
            decor.addView(it, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
    }

    /** First draw enables exit; on Android 12+ the native covering view must also be gone. */
    fun onContentDrawn() {
        if (contentDrawReported) return
        contentDrawReported = true
        event("content_draw_delivered")
        if (isComplete) return
        if (artwork == null || disposed || stopped || !ValueAnimator.areAnimatorsEnabled()) {
            completeArtwork("content_unavailable_or_reduced_motion")
            return
        }
        perform(exitPolicy.onContentDrawn())
        if (exitPolicy.awaitsNativeCallback) {
            // Not a normal-path hold: bound a missing OEM callback after actual content draw.
            // A late native callback still removes its native view even after this expires.
            callbackView?.postDelayed(missingNativeExit, 1_200L)
        }
    }

    private fun perform(action: Action, finishReason: String = "complete") {
        when (action) {
            Action.NONE -> Unit
            Action.SCHEDULE_FADE -> {
                callbackView?.removeCallbacks(missingNativeExit)
                if (nativeExitRequired) {
                    // The next frame can present artwork before its alpha starts changing.
                    callbackView?.postOnAnimation(startArtworkOnFrame)
                } else {
                    startArtworkOnFrame.run()
                }
            }
            Action.START_FADE -> startArtworkFade()
            Action.FINISH -> completeArtwork(finishReason)
        }
    }

    private fun startArtworkFade() {
        val view = artwork
        if (view == null || disposed || stopped || activity.isFinishing || activity.isDestroyed) {
            completeArtwork("lifecycle_interrupted")
            return
        }
        event("art_fade_start")
        view.animate().alpha(0f).setDuration(380L)
            .setInterpolator(PathInterpolator(.2f, 0f, 0f, 1f))
            .setListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) {
                    event("art_fade_end")
                    completeArtwork("animation_end")
                }
                override fun onAnimationCancel(animation: Animator) = completeArtwork("animation_cancel")
            }).start()
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun installPlatformExit() {
        activity.splashScreen.setOnExitAnimationListener { splash ->
            event("native_exit_received")
            exitPolicy.onNativeExitReceived()
            callbackView?.removeCallbacks(missingNativeExit)
            activeView = splash
            removeActiveSplash = { splash.remove() }
            if (disposed || stopped || isComplete || activity.isFinishing || activity.isDestroyed ||
                !ValueAnimator.areAnimatorsEnabled()
            ) {
                // Cleanup owns both layers, including a callback arriving after the watchdog.
                completeArtwork("late_native_or_lifecycle_or_reduced_motion")
                return@setOnExitAnimationListener
            }
            splash.animate()
                .alpha(0f)
                .setDuration(90L)
                .setInterpolator(PathInterpolator(.2f, 0f, 0f, 1f))
                .setListener(object : AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: Animator) = dismissNative()
                    override fun onAnimationCancel(animation: Animator) = dismissNative()
                })
                .start()
        }
    }

    /** A lifecycle interruption must not leave a retained view, frame callback or timer. */
    fun stop() {
        stopped = true
        completeArtwork("stop")
    }

    fun resume() {
        stopped = false
    }

    fun finishForTaskEntry() {
        completeArtwork("task_entry")
    }

    fun applyAppearance(dark: Boolean, pureBlack: Boolean) {
        artwork?.setAppearance(dark, pureBlack)
    }

    fun dispose() {
        disposed = true
        onComplete = null
        completeArtwork("destroy")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) clearPlatformExit()
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun clearPlatformExit() {
        activity.splashScreen.clearOnExitAnimationListener()
    }

    private fun dismissNative() {
        val view = activeView
        val remove = removeActiveSplash
        activeView = null
        removeActiveSplash = null
        view?.animate()?.setListener(null)?.cancel()
        if (remove != null) {
            remove()
            event("native_removed")
            callbackView?.removeCallbacks(missingNativeExit)
            perform(exitPolicy.onNativeRemoved())
        }
    }

    private fun removeArtwork() {
        val view = artwork
        artwork = null
        view?.animate()?.setListener(null)?.cancel()
        (view?.parent as? ViewGroup)?.removeView(view)
    }

    private fun completeArtwork(reason: String) {
        exitPolicy.finish()
        callbackView?.removeCallbacks(missingNativeExit)
        callbackView?.removeCallbacks(startArtworkOnFrame)
        removeArtwork()
        dismissNative()
        if (completionDispatched) return
        completionDispatched = true
        event("art_removed", reason)
        if (!disposed) onComplete?.invoke()
        onComplete = null
    }

    private fun event(name: String, reason: String? = null) {
        val detail = if (reason == null) "" else " reason=$reason"
        Log.i("LuoShuStartup", "event=$name elapsedMs=${SystemClock.elapsedRealtime() - startedAt}$detail")
    }
}
