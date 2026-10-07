package io.github.xgl34222220.luoshu.ui.launch

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Activity
import android.os.Build
import android.view.View
import android.view.animation.PathInterpolator
import androidx.annotation.RequiresApi

/** Owns only the native starting window. Content is never held for a timer or root work. */
internal class LuoShuLaunchController(private val activity: Activity) {
    var isComplete: Boolean = false
        private set

    private var activeView: View? = null
    private var removeActiveSplash: (() -> Unit)? = null
    private var onComplete: (() -> Unit)? = null
    private var disposed = false
    private var stopped = false

    fun install(skipExitAnimation: Boolean, onComplete: () -> Unit) {
        this.onComplete = onComplete
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !skipExitAnimation) {
            installPlatformExit()
        } else {
            // Recreation/task entry uses the system default transition, never another launch page.
            finish()
        }
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun installPlatformExit() {
        activity.splashScreen.setOnExitAnimationListener { splash ->
            if (disposed || stopped || activity.isFinishing || activity.isDestroyed ||
                !ValueAnimator.areAnimatorsEnabled()
            ) {
                splash.remove()
                finish()
                return@setOnExitAnimationListener
            }

            activeView = splash
            removeActiveSplash = { splash.remove() }
            splash.animate()
                .alpha(0f)
                .setDuration(180L)
                .setInterpolator(PathInterpolator(.2f, 0f, 0f, 1f))
                .setListener(object : AnimatorListenerAdapter() {
                    override fun onAnimationEnd(animation: Animator) = dismiss()
                    override fun onAnimationCancel(animation: Animator) = dismiss()
                })
                .start()
        }
    }

    /** A lifecycle interruption must not leave a retained native view or animation behind. */
    fun stop() {
        stopped = true
        dismiss()
    }

    fun resume() {
        stopped = false
    }

    fun dispose() {
        disposed = true
        onComplete = null
        dismiss()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) clearPlatformExit()
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun clearPlatformExit() {
        activity.splashScreen.clearOnExitAnimationListener()
    }

    private fun dismiss() {
        val view = activeView
        val remove = removeActiveSplash
        activeView = null
        removeActiveSplash = null
        view?.animate()?.setListener(null)?.cancel()
        remove?.invoke()
        // Only an actual splash removal completes the native exit. onStop before first draw
        // must not mark an unseen splash as ready and allow a permission dialog to race it.
        if (remove != null) finish()
    }

    private fun finish() {
        if (isComplete) return
        isComplete = true
        if (!disposed) onComplete?.invoke()
        onComplete = null
    }
}
