package io.github.xgl34222220.luoshu

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
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

class MainActivity : ComponentActivity() {
    private var openTaskCenter by mutableStateOf(false)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        configureHighRefreshRate()
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
        requestImportNotificationPermission()
        setContent {
            if (openTaskCenter) TaskCenterHost() else LuoShuHost()
        }
    }

    override fun onResume() {
        super.onResume()
        // 部分 ROM 会在应用切回前台时重置窗口刷新率偏好，再次提交最高刷新率请求。
        configureHighRefreshRate()
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
    }

    private fun configureHighRefreshRate() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.VANILLA_ICE_CREAM) {
            window.setFrameRateBoostOnTouchEnabled(true)
        }
        val targetDisplay: Display? = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            display
        } else {
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay
        }
        val maximum = targetDisplay?.supportedModes
            ?.asSequence()
            ?.map { it.refreshRate }
            ?.filter { it.isFinite() && it >= 60f }
            ?.maxOrNull()
            ?: return
        val attributes = window.attributes
        if (kotlin.math.abs(attributes.preferredRefreshRate - maximum) >= 0.5f) {
            attributes.preferredRefreshRate = maximum
            window.attributes = attributes
        }
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
