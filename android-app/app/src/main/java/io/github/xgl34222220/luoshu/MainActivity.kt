package io.github.xgl34222220.luoshu

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

class MainActivity : ComponentActivity() {
    private var openTaskCenter by mutableStateOf(false)
    private val displayPerformanceController by lazy(LazyThreadSafetyMode.NONE) {
        DisplayPerformanceController(this)
    }

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
        displayPerformanceController.onStart()
    }

    override fun onResume() {
        super.onResume()
        displayPerformanceController.onResume()
    }

    override fun onPause() {
        displayPerformanceController.onPause()
        super.onPause()
    }

    override fun onStop() {
        displayPerformanceController.onStop()
        super.onStop()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        displayPerformanceController.onWindowFocusChanged(hasFocus)
    }

    override fun onPictureInPictureModeChanged(
        isInPictureInPictureMode: Boolean,
        newConfig: Configuration,
    ) {
        super.onPictureInPictureModeChanged(isInPictureInPictureMode, newConfig)
        displayPerformanceController.onPictureInPictureModeChanged(isInPictureInPictureMode)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
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
