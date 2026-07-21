package io.github.xgl34222220.luoshu

import android.app.Activity
import android.content.res.Configuration
import android.hardware.display.DisplayManager
import android.os.Build
import android.view.Display
import kotlin.math.abs

internal data class DisplayModeCandidate(
    val modeId: Int,
    val width: Int,
    val height: Int,
    val refreshRate: Float,
)

internal fun selectHighestSameResolutionMode(
    modes: List<DisplayModeCandidate>,
    current: DisplayModeCandidate,
): DisplayModeCandidate? = modes
    .asSequence()
    .filter { it.width == current.width && it.height == current.height }
    .maxWithOrNull(
        compareBy<DisplayModeCandidate> { it.refreshRate }
            .thenBy { if (it.modeId == current.modeId) 1 else 0 },
    )

/** Maintains the focused LuoShu window's highest same-resolution refresh-rate preference. */
internal class DisplayPerformanceController(
    private val activity: Activity,
) : DisplayManager.DisplayListener {
    private val displayManager = activity.getSystemService(DisplayManager::class.java)
    private var listenerRegistered = false
    private var resumed = false
    private var focused = false
    private var pictureInPicture = false
    private var appliedDisplayId = Display.INVALID_DISPLAY
    private var appliedModeId = 0
    private var appliedRefreshRate = 0f

    fun onStart() {
        if (!listenerRegistered) {
            displayManager.registerDisplayListener(this, null)
            listenerRegistered = true
        }
        applyPreference()
    }

    fun onResume() {
        resumed = true
        applyPreference(force = true)
    }

    fun onPause() {
        resumed = false
        clearPreference()
    }

    fun onStop() {
        resumed = false
        focused = false
        clearPreference()
        if (listenerRegistered) {
            displayManager.unregisterDisplayListener(this)
            listenerRegistered = false
        }
    }

    fun onWindowFocusChanged(hasFocus: Boolean) {
        focused = hasFocus
        if (hasFocus) applyPreference(force = true) else clearPreference()
    }

    fun onPictureInPictureModeChanged(inPictureInPictureMode: Boolean) {
        pictureInPicture = inPictureInPictureMode
        if (inPictureInPictureMode) clearPreference() else applyPreference(force = true)
    }

    override fun onDisplayAdded(displayId: Int) = Unit

    override fun onDisplayRemoved(displayId: Int) {
        if (displayId == appliedDisplayId) clearPreference()
    }

    override fun onDisplayChanged(displayId: Int) {
        val currentDisplayId = activity.window.decorView.display?.displayId ?: return
        if (displayId == currentDisplayId) applyPreference(force = true)
    }

    private fun applyPreference(force: Boolean = false) {
        if (!resumed || !focused || pictureInPicture || activity.isFinishing) {
            clearPreference()
            return
        }
        val display = activity.window.decorView.display ?: return
        val currentMode = display.mode.toCandidate()
        val target = selectHighestSameResolutionMode(
            modes = display.supportedModes.map(Display.Mode::toCandidate),
            current = currentMode,
        ) ?: return
        if (
            !force &&
            display.displayId == appliedDisplayId &&
            target.modeId == appliedModeId &&
            abs(target.refreshRate - appliedRefreshRate) < REFRESH_EPSILON
        ) {
            return
        }

        val attributes = activity.window.attributes
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            // Modern Android maps the rate preference to Surface frame-rate selection without
            // requesting another resolution.
            attributes.preferredDisplayModeId = 0
            attributes.preferredRefreshRate = target.refreshRate
        } else {
            // Older OEM display managers are more reliable with the exact same-resolution mode id.
            attributes.preferredDisplayModeId = target.modeId
            attributes.preferredRefreshRate = 0f
        }
        activity.window.attributes = attributes
        appliedDisplayId = display.displayId
        appliedModeId = target.modeId
        appliedRefreshRate = target.refreshRate
    }

    private fun clearPreference() {
        if (appliedDisplayId == Display.INVALID_DISPLAY && appliedRefreshRate == 0f) return
        val attributes = activity.window.attributes
        if (attributes.preferredDisplayModeId != 0 || attributes.preferredRefreshRate != 0f) {
            attributes.preferredDisplayModeId = 0
            attributes.preferredRefreshRate = 0f
            activity.window.attributes = attributes
        }
        appliedDisplayId = Display.INVALID_DISPLAY
        appliedModeId = 0
        appliedRefreshRate = 0f
    }

    private fun Display.Mode.toCandidate(): DisplayModeCandidate = DisplayModeCandidate(
        modeId = modeId,
        width = physicalWidth,
        height = physicalHeight,
        refreshRate = refreshRate,
    )

    private companion object {
        const val REFRESH_EPSILON = 0.1f
    }
}
