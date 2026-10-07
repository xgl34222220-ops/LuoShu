package io.github.xgl34222220.luoshu.ui.launch

import android.animation.Animator
import android.animation.AnimatorListenerAdapter
import android.animation.ValueAnimator
import android.app.Activity
import android.os.Build
import android.view.View
import android.view.ViewGroup
import android.view.animation.PathInterpolator
import androidx.annotation.RequiresApi

/** Native start plus first-frame artwork; no timer, input shield, or dependency on root work. */
internal class LuoShuLaunchController(private val activity: Activity) {
    var isComplete: Boolean = false
        private set

    private var activeView: View? = null
    private var removeActiveSplash: (() -> Unit)? = null
    private var onComplete: (() -> Unit)? = null
    private var disposed = false
    private var stopped = false
    private var artwork: LuoShuLaunchArtView? = null
    private var showArtwork = false
    private var artworkExitStarted = false

    fun install(skipExitAnimation: Boolean, onComplete: () -> Unit) {
        this.onComplete = onComplete
        showArtwork = !skipExitAnimation && ValueAnimator.areAnimatorsEnabled()
        if (!showArtwork) {
            finish()
            return
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) installPlatformExit()
    }

    /** Attach after setContent, above the first App frame, with touch and a11y passing through. */
    fun attachArtwork() {
        if (!showArtwork || disposed || stopped) return
        val decor = activity.window.decorView as? ViewGroup ?: run {
            finish()
            return
        }
        artwork = LuoShuLaunchArtView(activity).also {
            decor.addView(it, ViewGroup.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT))
        }
    }

    /** The very first real draw starts the fade, regardless of native/OEM callback timing. */
    fun onContentDrawn() {
        if (artworkExitStarted || isComplete) return
        artworkExitStarted = true
        val view = artwork
        if (view == null || disposed || stopped || !ValueAnimator.areAnimatorsEnabled()) {
            removeArtwork()
            finish()
            return
        }
        view.animate().alpha(0f).setDuration(380L)
            .setInterpolator(PathInterpolator(.2f, 0f, 0f, 1f))
            .setListener(object : AnimatorListenerAdapter() {
                override fun onAnimationEnd(animation: Animator) = completeArtwork()
                override fun onAnimationCancel(animation: Animator) = completeArtwork()
            }).start()
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun installPlatformExit() {
        activity.splashScreen.setOnExitAnimationListener { splash ->
            if (disposed || stopped || isComplete || activity.isFinishing || activity.isDestroyed ||
                !ValueAnimator.areAnimatorsEnabled()
            ) {
                splash.remove()
                return@setOnExitAnimationListener
            }

            activeView = splash
            removeActiveSplash = { splash.remove() }
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

    /** A lifecycle interruption must not leave a retained native view or animation behind. */
    fun stop() {
        stopped = true
        dismissNative()
        completeArtwork()
    }

    fun resume() {
        stopped = false
    }

    fun finishForTaskEntry() {
        completeArtwork()
    }

    fun applyAppearance(dark: Boolean, pureBlack: Boolean) {
        artwork?.setAppearance(dark, pureBlack)
    }

    fun dispose() {
        disposed = true
        onComplete = null
        dismissNative()
        completeArtwork()
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
        remove?.invoke()
    }

    private fun removeArtwork() {
        val view = artwork
        artwork = null
        view?.animate()?.setListener(null)?.cancel()
        (view?.parent as? ViewGroup)?.removeView(view)
    }

    private fun completeArtwork() {
        removeArtwork()
        // Do not let a late/missing native callback retain this layer or a permission prompt.
        dismissNative()
        finish()
    }

    private fun finish() {
        if (isComplete) return
        isComplete = true
        if (!disposed) onComplete?.invoke()
        onComplete = null
    }
}
