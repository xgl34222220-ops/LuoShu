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
import android.widget.FrameLayout
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.platform.ViewCompositionStrategy
import androidx.lifecycle.ViewModelProvider
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceViewModel
import io.github.xgl34222220.luoshu.ui.launch.LuoShuNativeShellPolicy
import io.github.xgl34222220.luoshu.ui.launch.LuoShuNativeShellView
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.annotation.RequiresApi
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
    private var nativeShellPolicy: LuoShuNativeShellPolicy? = null
    private var shellCommitCallback: Runnable? = null
    private var shellCommitObserver: ViewTreeObserver? = null
    private var shellDrawListener: ViewTreeObserver.OnPreDrawListener? = null
    private var shellHandoffCallback: Runnable? = null
    private var pendingAppearance: AppearanceSettings? = null
    // Cold launch only: the diffuse glass shell drawn above the already composed home.
    private var launchShellVisible by mutableStateOf(false)
    private var launchShellTextVisible = false
    // One composition call site on both paths preserves rememberSaveable keys on recreation.
    private val appContent: @Composable () -> Unit = {
        if (openTaskCenter) TaskCenterHost() else LuoShuHost(
            firstFrameCommitted = firstFrameCommitted,
            launchShellVisible = launchShellVisible,
            launchShellTextVisible = launchShellTextVisible,
            onLaunchShellFinished = ::finishLaunchShell,
        )
    }
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
        val useNativeShell = LuoShuNativeShellPolicy.eligible(
            Build.VERSION.SDK_INT, savedInstanceState != null, openTaskCenter,
        )
        if (useNativeShell) nativeShellPolicy = LuoShuNativeShellPolicy()
        // Same eligibility as the native shell, on every API: never on restore or task entry.
        launchShellVisible = savedInstanceState == null && !openTaskCenter
        launchShellTextVisible = useNativeShell
        launchController.install(
            startedAt = activityStartedAt,
            onComplete = ::requestImportNotificationPermissionWhenReady,
            nativeShell = useNativeShell,
        )
        observeDisplayPreference()
        if (useNativeShell && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            installNativeShell(activityStartedAt)
        } else {
            setContent(content = appContent)
            observeFirstDraw(activityStartedAt)
        }
    }

    @RequiresApi(Build.VERSION_CODES.S)
    private fun installNativeShell(startedAt: Long) {
        val policy = checkNotNull(nativeShellPolicy)
        val root = FrameLayout(this)
        root.addView(LuoShuNativeShellView(this), FrameLayout.LayoutParams(-1, -1))
        setContentView(root)
        val decor = window.decorView
        // The first callback belongs only to the preparation frame. No home/blur/permission release.
        shellCommitCallback = Runnable {
            if (isFinishing || isDestroyed || !policy.onShellSubmitted()) return@Runnable
            Log.i("LuoShuStartup", "event=native_shell_submitted elapsedMs=${SystemClock.elapsedRealtime() - startedAt} phase=swap_chain")
            scheduleNativeShellHandoff(root, policy, startedAt, softwareFallback = false)
        }.also {
            shellCommitObserver = decor.viewTreeObserver
            decor.viewTreeObserver.registerFrameCommitCallback(it)
        }
        shellDrawListener = ViewTreeObserver.OnPreDrawListener {
            if (!decor.isHardwareAccelerated) {
                // Cancel only this preparation traversal. Software follows the real-content
                // legacy draw path without ever presenting or claiming a submitted shell.
                scheduleNativeShellHandoff(root, policy, startedAt, softwareFallback = true)
                false
            } else {
                true
            }
        }.also { decor.viewTreeObserver.addOnPreDrawListener(it) }
    }

    private fun scheduleNativeShellHandoff(
        root: FrameLayout,
        policy: LuoShuNativeShellPolicy,
        startedAt: Long,
        softwareFallback: Boolean,
    ) {
        if (shellHandoffCallback != null || isFinishing || isDestroyed) return
        shellHandoffCallback = Runnable {
            shellHandoffCallback = null
            if (isFinishing || isDestroyed || !policy.beginContent(softwareFallback)) return@Runnable
            removeNativeShellObservers()
            val appearance = pendingAppearance
            pendingAppearance = null
            if (appearance != null) {
                // Seed the same Activity-owned VM used by Compose: no default-theme interstitial.
                ViewModelProvider(this, AppearanceViewModel.InitialAppearanceFactory(application, appearance))
                    .get(AppearanceViewModel::class.java)
            }
            applyWindowAppearance(appearance ?: AppearanceSettings())
            val content = ComposeView(this).apply {
                setViewCompositionStrategy(ViewCompositionStrategy.DisposeOnViewTreeLifecycleDestroyed)
                setContent(appContent)
            }
            // Mutate children in one main-thread turn. The Window/Surface never detaches or clears.
            // The previously submitted buffer can remain while this complete content is rendered.
            root.removeAllViews()
            root.addView(content, FrameLayout.LayoutParams(-1, -1))
            observeFirstDraw(startedAt)
            Log.i("LuoShuStartup", "event=full_content_attached elapsedMs=${SystemClock.elapsedRealtime() - startedAt} appearanceKnown=${appearance != null} softwareFallback=$softwareFallback")
        }.also { window.decorView.post(it) }
    }

    private fun removeNativeShellObservers() {
        shellCommitCallback?.let { callback ->
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                shellCommitObserver?.takeIf { it.isAlive }?.unregisterFrameCommitCallback(callback)
                window.decorView.viewTreeObserver.takeIf { it.isAlive }?.unregisterFrameCommitCallback(callback)
            }
        }
        shellCommitCallback = null
        shellCommitObserver = null
        shellDrawListener?.let { listener ->
            window.decorView.viewTreeObserver.takeIf { it.isAlive }?.removeOnPreDrawListener(listener)
        }
        shellDrawListener = null
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
        nativeShellPolicy?.dispose()
        shellHandoffCallback?.let(window.decorView::removeCallbacks)
        shellHandoffCallback = null
        removeNativeShellObservers()
        pendingAppearance = null
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
        if (openTaskCenter) {
            launchShellVisible = false
            launchController.finishForTaskEntry()
        }
        requestImportNotificationPermissionWhenReady()
    }

    private fun finishLaunchShell() {
        if (!launchShellVisible) return
        launchShellVisible = false
        Log.i("LuoShuStartup", "event=launch_shell_finished")
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

    private fun applyWindowAppearance(settings: AppearanceSettings) {
        displayPerformanceController.setHighRefreshEnabled(settings.highRefreshRate)
        val dark = when (settings.themeMode) {
            ThemeMode.LIGHT -> false
            ThemeMode.DARK -> true
            ThemeMode.SYSTEM -> resources.configuration.uiMode and
                Configuration.UI_MODE_NIGHT_MASK == Configuration.UI_MODE_NIGHT_YES
        }
        launchController.applyAppearance(dark, dark && settings.amoledBlack, settings.glassEnabled)
    }

    private fun observeDisplayPreference() {
        lifecycleScope.launch {
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                appearanceRepository.settings
                    .distinctUntilChanged()
                    .collect { settings ->
                        val phase = nativeShellPolicy?.phase
                        if (phase == LuoShuNativeShellPolicy.Phase.SHELL ||
                            phase == LuoShuNativeShellPolicy.Phase.SHELL_SUBMITTED
                        ) {
                            pendingAppearance = settings
                        } else {
                            applyWindowAppearance(settings)
                        }
                    }
            }
        }
    }
}

