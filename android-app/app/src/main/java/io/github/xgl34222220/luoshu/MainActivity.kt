package io.github.xgl34222220.luoshu

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import android.content.res.Configuration
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.util.Log
import android.view.ViewTreeObserver
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceRepository
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.launch.LuoShuLaunchController
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private var openTaskCenter by mutableStateOf(false)
    private var firstDrawListener: ViewTreeObserver.OnDrawListener? = null
    private var firstContentDrawn = false
    private val launchController by lazy(LazyThreadSafetyMode.NONE) {
        LuoShuLaunchController(this)
    }
    private val displayPerformanceController by lazy(LazyThreadSafetyMode.NONE) {
        DisplayPerformanceController(this)
    }
    private val appearanceRepository by lazy(LazyThreadSafetyMode.NONE) {
        AppearanceRepository(applicationContext)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        val activityStartedAt = SystemClock.elapsedRealtime()
        // The OS has already drawn the launch theme. Keep only the real page background
        // inside the Activity so rotation and navigation never redraw a second splash.
        setTheme(R.style.Theme_LuoShuHybrid)
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        openTaskCenter = intent.getBooleanExtra(EXTRA_OPEN_TASK_CENTER, false)
        launchController.install(
            skipExitAnimation = savedInstanceState != null || openTaskCenter,
            startedAt = activityStartedAt,
            onComplete = ::requestImportNotificationPermissionWhenReady,
        )
        observeDisplayPreference()
        setContent {
            if (openTaskCenter) TaskCenterHost() else LuoShuHost()
        }
        launchController.attachArtwork()
        observeFirstDraw(activityStartedAt)
    }

    private fun observeFirstDraw(startedAt: Long) {
        val view = window.decorView
        var reported = false
        val listener = ViewTreeObserver.OnDrawListener {
            if (!reported) {
                reported = true
                val elapsed = SystemClock.elapsedRealtime() - startedAt
                Log.i("LuoShuStartup", "event=first_decor_draw elapsedMs=$elapsed activityFirstDrawMs=$elapsed")
                // Android forbids removing an OnDrawListener while dispatching onDraw.
                view.post {
                    removeFirstDrawListener()
                    firstContentDrawn = true
                    launchController.onContentDrawn()
                    requestImportNotificationPermissionWhenReady()
                }
            }
        }
        firstDrawListener = listener
        view.viewTreeObserver.addOnDrawListener(listener)
    }

    private fun removeFirstDrawListener() {
        firstDrawListener?.let { listener ->
            val observer = window.decorView.viewTreeObserver
            if (observer.isAlive) observer.removeOnDrawListener(listener)
        }
        firstDrawListener = null
    }

    override fun onDestroy() {
        removeFirstDrawListener()
        launchController.dispose()
        super.onDestroy()
    }

    override fun onStart() {
        super.onStart()
        displayPerformanceController.onStart()
    }

    override fun onResume() {
        super.onResume()
        displayPerformanceController.onResume()
        launchController.resume()
        requestImportNotificationPermissionWhenReady()
    }

    override fun onPause() {
        displayPerformanceController.onPause()
        super.onPause()
    }

    override fun onStop() {
        displayPerformanceController.onStop()
        super.onStop()
        launchController.stop()
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
        if (openTaskCenter) launchController.finishForTaskEntry()
        requestImportNotificationPermissionWhenReady()
    }

    private fun requestImportNotificationPermissionWhenReady() {
        if (!firstContentDrawn || !launchController.isComplete || openTaskCenter ||
            isFinishing || isDestroyed || !lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        ) return

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU &&
            ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) !=
            PackageManager.PERMISSION_GRANTED
        ) {
            // One launch-time explanation is enough. Denial, rotation, and background return
            // should not turn opening the font library into a repeated permission prompt.
            val permissions = getSharedPreferences("launch_permissions", MODE_PRIVATE)
            if (permissions.getBoolean("import_notifications_requested", false)) return
            permissions.edit().putBoolean("import_notifications_requested", true).apply()
            ActivityCompat.requestPermissions(
                this,
                arrayOf(Manifest.permission.POST_NOTIFICATIONS),
                14331,
            )
        }
    }

    private fun observeDisplayPreference() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                appearanceRepository.settings
                    .map { settings -> Triple(settings.highRefreshRate, settings.themeMode, settings.amoledBlack) }
                    .distinctUntilChanged()
                    .collect { (highRefresh, themeMode, amoledBlack) ->
                        displayPerformanceController.setHighRefreshEnabled(highRefresh)
                        val dark = when (themeMode) {
                            ThemeMode.LIGHT -> false
                            ThemeMode.DARK -> true
                            ThemeMode.SYSTEM -> resources.configuration.uiMode and
                                Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
                        }
                        launchController.applyAppearance(dark, dark && amoledBlack)
                    }
            }
        }
    }
}
