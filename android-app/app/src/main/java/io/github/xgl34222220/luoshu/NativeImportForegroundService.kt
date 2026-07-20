package io.github.xgl34222220.luoshu

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.content.ContextCompat
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

internal const val EXTRA_OPEN_TASK_CENTER = "io.github.xgl34222220.luoshu.OPEN_TASK_CENTER"

private const val IMPORT_NOTIFICATION_CHANNEL = "font_import"
private const val IMPORT_NOTIFICATION_ID = 14331

internal enum class NativeImportNotificationAction(
    val intentAction: String,
    val label: String,
) {
    PAUSE("io.github.xgl34222220.luoshu.import.PAUSE", "暂停"),
    RESUME("io.github.xgl34222220.luoshu.import.RESUME", "继续"),
    CANCEL("io.github.xgl34222220.luoshu.import.CANCEL", "取消"),
    RETRY("io.github.xgl34222220.luoshu.import.RETRY", "重试失败项"),
    CLEAR("io.github.xgl34222220.luoshu.import.CLEAR", "清除记录"),
}

internal data class NativeImportNotificationSpec(
    val title: String,
    val message: String,
    val total: Int,
    val processed: Int,
    val ongoing: Boolean,
    val actions: List<NativeImportNotificationAction>,
)

internal fun nativeImportNotificationSpec(state: NativeImportState): NativeImportNotificationSpec {
    val actions = when {
        state.busy -> listOf(NativeImportNotificationAction.PAUSE, NativeImportNotificationAction.CANCEL)
        state.paused -> listOf(NativeImportNotificationAction.RESUME, NativeImportNotificationAction.CANCEL)
        state.canRetryFailed -> listOf(NativeImportNotificationAction.RETRY, NativeImportNotificationAction.CLEAR)
        state.canClear -> listOf(NativeImportNotificationAction.CLEAR)
        else -> emptyList()
    }
    return NativeImportNotificationSpec(
        title = state.title,
        message = state.message,
        total = state.total,
        processed = state.processed,
        ongoing = state.busy,
        actions = actions,
    )
}

internal object NativeImportNotificationController {
    fun start(context: Context) {
        ensureChannel(context)
        ContextCompat.startForegroundService(context, Intent(context, NativeImportForegroundService::class.java))
    }

    fun cancel(context: Context) {
        context.stopService(Intent(context, NativeImportForegroundService::class.java))
        notificationManager(context).cancel(IMPORT_NOTIFICATION_ID)
    }

    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val channel = NotificationChannel(
            IMPORT_NOTIFICATION_CHANNEL,
            "字体导入",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "显示字体导入进度与任务控制"
            setShowBadge(false)
            enableVibration(false)
            setSound(null, null)
        }
        notificationManager(context).createNotificationChannel(channel)
    }

    fun buildNotification(context: Context, state: NativeImportState): Notification {
        val spec = nativeImportNotificationSpec(state)
        val openTasks = PendingIntent.getActivity(
            context,
            14331,
            Intent(context, MainActivity::class.java).apply {
                putExtra(EXTRA_OPEN_TASK_CENTER, true)
                addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
            },
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = Notification.Builder(context, IMPORT_NOTIFICATION_CHANNEL)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(spec.title)
            .setContentText(spec.message)
            .setStyle(Notification.BigTextStyle().bigText(spec.message))
            .setContentIntent(openTasks)
            .setCategory(Notification.CATEGORY_PROGRESS)
            .setOnlyAlertOnce(true)
            .setOngoing(spec.ongoing)
            .setAutoCancel(!spec.ongoing)
            .setShowWhen(false)

        if ((state.busy || state.paused) && spec.total > 0) {
            builder.setProgress(spec.total, spec.processed.coerceIn(0, spec.total), false)
        }
        spec.actions.forEach { action ->
            builder.addAction(
                notificationActionIcon(action),
                action.label,
                PendingIntent.getBroadcast(
                    context,
                    14400 + action.ordinal,
                    Intent(context, NativeImportActionReceiver::class.java).setAction(action.intentAction),
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                ),
            )
        }
        return builder.build()
    }

    fun notify(context: Context, state: NativeImportState) {
        notificationManager(context).notify(IMPORT_NOTIFICATION_ID, buildNotification(context, state))
    }

    private fun notificationActionIcon(action: NativeImportNotificationAction): Int = when (action) {
        NativeImportNotificationAction.PAUSE -> android.R.drawable.ic_media_pause
        NativeImportNotificationAction.RESUME -> android.R.drawable.ic_media_play
        NativeImportNotificationAction.CANCEL -> android.R.drawable.ic_menu_close_clear_cancel
        NativeImportNotificationAction.RETRY -> android.R.drawable.ic_popup_sync
        NativeImportNotificationAction.CLEAR -> android.R.drawable.ic_menu_delete
    }

    private fun notificationManager(context: Context): NotificationManager =
        context.getSystemService(NotificationManager::class.java)
}

internal class NativeImportForegroundService : Service() {
    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
    private var observerJob: Job? = null

    private val importViewModel: NativeImportViewModel
        get() = (application as LuoShuApplication).nativeImportViewModel

    override fun onCreate() {
        super.onCreate()
        NativeImportNotificationController.ensureChannel(this)
        importViewModel
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val initial = importViewModel.state.takeIf { it.phase != NativeImportPhase.IDLE }
            ?: NativeImportState(phase = NativeImportPhase.QUEUED, message = "正在准备字体导入任务")
        startAsForeground(initial)
        observeImportState(startId)
        return START_STICKY
    }

    private fun observeImportState(startId: Int) {
        observerJob?.cancel()
        observerJob = serviceScope.launch {
            var idleChecks = 0
            while (isActive) {
                val state = importViewModel.state
                if (state.phase == NativeImportPhase.IDLE) {
                    idleChecks += 1
                    if (idleChecks >= 20) {
                        stopForeground(STOP_FOREGROUND_REMOVE)
                        stopSelf(startId)
                        return@launch
                    }
                } else {
                    idleChecks = 0
                    NativeImportNotificationController.notify(this@NativeImportForegroundService, state)
                    if (!state.busy) {
                        stopForeground(STOP_FOREGROUND_DETACH)
                        stopSelf(startId)
                        return@launch
                    }
                }
                delay(250L)
            }
        }
    }

    private fun startAsForeground(state: NativeImportState) {
        val notification = NativeImportNotificationController.buildNotification(this, state)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(IMPORT_NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(IMPORT_NOTIFICATION_ID, notification)
        }
    }

    override fun onDestroy() {
        observerJob?.cancel()
        serviceScope.cancel()
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

internal class NativeImportActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = NativeImportNotificationAction.entries.firstOrNull { it.intentAction == intent.action } ?: return
        val application = context.applicationContext as? LuoShuApplication ?: return
        val result = goAsync()
        val scope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)
        scope.launch {
            try {
                val viewModel = application.nativeImportViewModel
                if (action == NativeImportNotificationAction.RESUME || action == NativeImportNotificationAction.RETRY) {
                    runCatching { NativeImportNotificationController.start(application) }
                }
                var attempts = 0
                while (!actionReady(action, viewModel.state) && attempts < 60) {
                    delay(100L)
                    attempts += 1
                }
                when (action) {
                    NativeImportNotificationAction.PAUSE -> viewModel.pauseImport()
                    NativeImportNotificationAction.RESUME -> viewModel.resumeImport()
                    NativeImportNotificationAction.CANCEL -> viewModel.cancelImport()
                    NativeImportNotificationAction.RETRY -> viewModel.retryFailed()
                    NativeImportNotificationAction.CLEAR -> {
                        viewModel.clearRecord()
                        NativeImportNotificationController.cancel(application)
                    }
                }
            } finally {
                result.finish()
                scope.cancel()
            }
        }
    }

    private fun actionReady(action: NativeImportNotificationAction, state: NativeImportState): Boolean = when (action) {
        NativeImportNotificationAction.PAUSE -> state.canPause
        NativeImportNotificationAction.RESUME -> state.canResume
        NativeImportNotificationAction.CANCEL -> state.canCancel
        NativeImportNotificationAction.RETRY -> state.canRetryFailed
        NativeImportNotificationAction.CLEAR -> state.canClear
    }
}
