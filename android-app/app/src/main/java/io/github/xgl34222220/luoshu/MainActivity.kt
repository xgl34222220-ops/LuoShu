package io.github.xgl34222220.luoshu

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.display.DisplayManager
import android.os.Build
import android.os.Bundle
import android.view.Display
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlin.math.abs

class MainActivity : ComponentActivity(), DisplayManager.DisplayListener {
    private var openTaskCenter by mutableStateOf(false)
    private val displayManager by lazy(LazyThreadSafetyMode.NONE) {
        getSystemService(DisplayManager::class.java)
    }
    private var displayListenerRegistered = false
    private var resumed = false
    private var focused = false
    private var appliedDisplayId = Display.INVALID_DISPLAY
    private var appliedModeId = 0
    private var appliedRefreshRate = 0f

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
        requestImportNotificationPermission()
        setContent {
            if (openTaskCenter) TaskCenterHost() else LuoShuHost()
        }
    }

    override fun onStart() {
        super.onStart()
        if (!displayListenerRegistered) {
            displayManager.registerDisplayListener(this, null)
            displayListenerRegistered = true
        }
        applyHighestRefreshRate()
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        applyHighestRefreshRate()
    }

    override fun onPause() {
        resumed = false
        clearRefreshRatePreference()
        super.onPause()
    }

    override fun onStop() {
        resumed = false
        focused = false
        clearRefreshRatePreference()
        if (displayListenerRegistered) {
            displayManager.unregisterDisplayListener(this)
            displayListenerRegistered = false
        }
        super.onStop()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        focused = hasFocus
        if (hasFocus) applyHighestRefreshRate(force = true) else clearRefreshRatePreference()
    }

    override fun onDisplayAdded(displayId: Int) = Unit

    override fun onDisplayRemoved(displayId: Int) {
        if (displayId == appliedDisplayId) clearRefreshRatePreference()
    }

    override fun onDisplayChanged(displayId: Int) {
        val currentDisplayId = window.decorView.display?.displayId ?: return
        if (displayId == currentDisplayId) applyHighestRefreshRate(force = true)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
    }

    private fun applyHighestRefreshRate(force: Boolean = false) {
        if (!resumed || !focused || isInPictureInPictureMode) {
            clearRefreshRatePreference()
            return
        }
        val display = window.decorView.display ?: return
        val currentMode = display.mode
        val targetMode = display.supportedModes
            .asSequence()
            .filter {
                it.physicalWidth == currentMode.physicalWidth &&
                    it.physicalHeight == currentMode.physicalHeight
            }
            .maxWithOrNull(
                compareBy<Display.Mode> { it.refreshRate }
                    .thenBy { if (it.modeId == currentMode.modeId) 1 else 0 },
            ) ?: return
        if (
            !force &&
            display.displayId == appliedDisplayId &&
            targetMode.modeId == appliedModeId &&
            abs(targetMode.refreshRate - appliedRefreshRate) < 0.1f
        ) {
            return
        }

        val attributes = window.attributes
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            attributes.preferredDisplayModeId = 0
            attributes.preferredRefreshRate = targetMode.refreshRate
        } else {
            attributes.preferredDisplayModeId = targetMode.modeId
            attributes.preferredRefreshRate = 0f
        }
        window.attributes = attributes
        appliedDisplayId = display.displayId
        appliedModeId = targetMode.modeId
        appliedRefreshRate = targetMode.refreshRate
    }

    private fun clearRefreshRatePreference() {
        if (appliedDisplayId == Display.INVALID_DISPLAY && appliedRefreshRate == 0f) return
        val attributes = window.attributes
        if (attributes.preferredDisplayModeId != 0 || attributes.preferredRefreshRate != 0f) {
            attributes.preferredDisplayModeId = 0
            attributes.preferredRefreshRate = 0f
            window.attributes = attributes
        }
        appliedDisplayId = Display.INVALID_DISPLAY
        appliedModeId = 0
        appliedRefreshRate = 0f
    }

    private fun requestImportNotificationPermission() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                14331,
            )
        }
    }
}
