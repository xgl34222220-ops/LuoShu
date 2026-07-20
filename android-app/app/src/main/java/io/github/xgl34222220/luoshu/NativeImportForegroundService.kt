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

internal const val EXTRA_OPEN_TASK_CENTER = "io.github.xgl34222220.luoshu.OPEN_TASK_CENTER"

private const val IMPORT_NOTIFICATION_CHANNEL = "font_import"
private const val IMPORT_NOTIFICATION_ID = 14331
private const val EXTRA_PHASE = "phase"
private const val EXTRA_TOTAL = "total"
private const val EXTRA_PROCESSED = "processed"
private const val EXTRA_IMPORTED = "imported"
private const val EXTRA_DUPLICATES = "duplicates"
private const val EXTRA_CANCELLED = "cancelled"
private const val EXTRA_FAILED_COUNT = "failed_count"
private const val EXTRA_MESSAGE = "message"
private const val EXTRA_CURRENT_FILE = "current_file"

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
        state.busy -> listOf(
            NativeImportNotificationAction.PAUSE,
            NativeImportNotificationAction.CANCEL,
        )
        state.paused -> listOf(
            NativeImportNotificationAction.RESUME,
            NativeImportNotificationAction.CANCEL,
        )
        state.canRetryFailed -> listOf(
            NativeImportNotificationAction.RETRY,
            NativeImportNotificationAction.CLEAR,
        )
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
    fun sync(context: Context, state: NativeImportState) {
        ensureChannel(context)
        if (state.phase == NativeImportPhase.IDLE) {
            context.stopService(Intent(context, NativeImportForegroundService::class.java))
            notificationManager(context).cancel(IMPORT_NOTIFICATION_ID)
            return
        }
        val intent = Intent(context, NativeImportForegroundService::class.java).apply {
            putExtra(EXTRA_PHASE, state.phase.wireName)
            putExtra(EXTRA_TOTAL, state.total)
            putExtra(EXTRA_PROCESSED, state.processed)
            putExtra(EXTRA_IMPORTED, state.imported)
            putExtra(EXTRA_DUPLICATES, state.duplicates)
            putExtra(EXTRA_CANCELLED, state.cancelled)
            putExtra(EXTRA_FAILED_COUNT, state.failed.size)
            putExtra(EXTRA_MESSAGE, state.message)
            putExtra(EXTRA_CURRENT_FILE, state.currentFile)
        }
        ContextCompat.startForegroundService(context, intent)
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
    private val importViewModel: NativeImportViewModel
        get() = (application as LuoShuApplication).nativeImportViewModel

    override fun onCreate() {
        super.onCreate()
        NativeImportNotificationController.ensureChannel(this)
        importViewModel
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val state = intent?.toImportState() ?: importViewModel.state.takeIf {
            it.phase != NativeImportPhase.IDLE
        } ?: NativeImportState(
            phase = NativeImportPhase.QUEUED,
            message = "正在恢复字体导入任务",
        )
        val notification = NativeImportNotificationController.buildNotification(this, state)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                IMPORT_NOTIFICATION_ID,
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            startForeground(IMPORT_NOTIFICATION_ID, notification)
        }

        return if (state.busy) {
            START_STICKY
        } else {
            stopForeground(STOP_FOREGROUND_DETACH)
            stopSelf(startId)
            START_NOT_STICKY
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null
}

internal class NativeImportActionReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val application = context.applicationContext as? LuoShuApplication ?: return
        application.nativeImportViewModel.handleExternalAction(intent.action.orEmpty())
    }
}

private fun Intent.toImportState(): NativeImportState {
    val phaseWire = getStringExtra(EXTRA_PHASE).orEmpty()
    val phase = NativeImportPhase.entries.firstOrNull { it.wireName == phaseWire }
        ?: NativeImportPhase.IDLE
    val failedCount = getIntExtra(EXTRA_FAILED_COUNT, 0).coerceAtLeast(0)
    return NativeImportState(
        phase = phase,
        total = getIntExtra(EXTRA_TOTAL, 0),
        processed = getIntExtra(EXTRA_PROCESSED, 0),
        imported = getIntExtra(EXTRA_IMPORTED, 0),
        duplicates = getIntExtra(EXTRA_DUPLICATES, 0),
        cancelled = getIntExtra(EXTRA_CANCELLED, 0),
        failed = List(failedCount) { "导入失败" },
        message = getStringExtra(EXTRA_MESSAGE).orEmpty().ifBlank { "字体导入任务" },
        currentFile = getStringExtra(EXTRA_CURRENT_FILE).orEmpty(),
    )
}
