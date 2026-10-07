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
import io.github.xgl34222220.luoshu.ui.launch.LuoShuFirstFramePolicy
import io.github.xgl34222220.luoshu.ui.launch.LuoShuFirstFramePolicy.DrawAction
import kotlinx.coroutines.flow.distinctUntilChanged
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private var openTaskCenter by mutableStateOf(false)
    private var firstDrawListener: ViewTreeObserver.OnDrawListener? = null
    private var firstDrawCallback: Runnable? = null
    private var firstFrameCommitCallback: Runnable? = null
    private var firstFrameCommitObserver: ViewTreeObserver? = null
    private val firstFramePolicy = LuoShuFirstFramePolicy()
    private var firstFrameCommitted by mutableStateOf(false)
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
            startedAt = activityStartedAt,
            onComplete = ::requestImportNotificationPermissionWhenReady,
        )
        observeDisplayPreference()
        setContent {
            if (openTaskCenter) TaskCenterHost() else LuoShuHost(firstFrameCommitted)
        }
        observeFirstDraw(activityStartedAt)
    }

    private fun observeFirstDraw(startedAt: Long) {
        val view = window.decorView
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            // Register before the first traversal: ViewRootImpl captures commit callbacks
            // before dispatching OnDraw. A scheduled draw is not a submitted frame.
            firstFrameCommitCallback = Runnable {
                firstFrameCommitCallback = null
                firstFrameCommitObserver = null
                deliverFirstFrame(startedAt, "first_frame_committed", "swap_chain")
            }.also { callback ->
                firstFrameCommitObserver = view.viewTreeObserver
                view.viewTreeObserver.registerFrameCommitCallback(callback)
            }
        }
        val listener = ViewTreeObserver.OnDrawListener {
            // isHardwareAccelerated is reliable during draw, after Window attachment.
            // API 28 and software rendering have no frame commit callback.
            val action = firstFramePolicy.onDraw(
                frameCommitSupported = Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q,
                hardwareAccelerated = view.isHardwareAccelerated,
            )
            if (action != DrawAction.NONE) {
                val elapsed = SystemClock.elapsedRealtime() - startedAt
                Log.i("LuoShuStartup", "event=first_decor_draw elapsedMs=$elapsed activityFirstDrawMs=$elapsed")
                // Android forbids removing an OnDrawListener while dispatching onDraw.
                firstDrawCallback = Runnable {
                    firstDrawCallback = null
                    removeFirstDrawListener()
                    if (!isFinishing && !isDestroyed && action == DrawAction.POST_DRAW_DELIVERY) {
                        removeFirstFrameCommitCallback()
                        val phase = if (view.isHardwareAccelerated) "legacy_draw_return" else "software_draw_return"
                        deliverFirstFrame(startedAt, "first_frame_draw_delivered", phase)
                    }
                }.also { view.post(it) }
            }
        }
        firstDrawListener = listener
        view.viewTreeObserver.addOnDrawListener(listener)
    }

    private fun deliverFirstFrame(startedAt: Long, event: String, phase: String) {
        if (isFinishing || isDestroyed || !firstFramePolicy.onFrameDelivered()) return
        Log.i("LuoShuStartup", "event=$event elapsedMs=${SystemClock.elapsedRealtime() - startedAt} phase=$phase")
        firstContentDrawn = true
        // The first frame contains the complete home and glass tint. Offscreen blur and
        // refraction may now be initialized without delaying that first Window buffer.
        firstFrameCommitted = true
        launchController.onContentDrawn()
        requestImportNotificationPermissionWhenReady()
    }

    private fun removeFirstFrameCommitCallback() {
        val callback = firstFrameCommitCallback
        firstFrameCommitCallback = null
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && callback != null) {
            // A pre-attachment observer can be merged into the attached Window observer.
            // Remove from both; a callback already queued is guarded by deliverFirstFrame.
            firstFrameCommitObserver?.takeIf { it.isAlive }?.unregisterFrameCommitCallback(callback)
            window.decorView.viewTreeObserver.takeIf { it.isAlive }?.unregisterFrameCommitCallback(callback)
        }
        firstFrameCommitObserver = null
    }

    private fun removeFirstDrawListener() {
        firstDrawListener?.let { listener ->
            val observer = window.decorView.viewTreeObserver
            if (observer.isAlive) observer.removeOnDrawListener(listener)
        }
        firstDrawListener = null
    }

    override fun onDestroy() {
        firstFramePolicy.dispose()
        firstDrawCallback?.let(window.decorView::removeCallbacks)
        firstDrawCallback = null
        removeFirstDrawListener()
        removeFirstFrameCommitCallback()
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
                    .distinctUntilChanged()
                    .collect { settings ->
                        displayPerformanceController.setHighRefreshEnabled(settings.highRefreshRate)
                        val dark = when (settings.themeMode) {
                            ThemeMode.LIGHT -> false
                            ThemeMode.DARK -> true
                            ThemeMode.SYSTEM -> resources.configuration.uiMode and
                                Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
                        }
                        launchController.applyAppearance(dark, dark && settings.amoledBlack, settings.glassEnabled)
                    }
            }
        }
    }
}
