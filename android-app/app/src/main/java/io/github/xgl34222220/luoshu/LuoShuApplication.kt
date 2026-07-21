package io.github.xgl34222220.luoshu

import android.app.Application
import android.os.SystemClock
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

internal class LuoShuApplication : Application(), ViewModelStoreOwner {
    override val viewModelStore: ViewModelStore = ViewModelStore()
    private val applicationScope = CoroutineScope(SupervisorJob() + Dispatchers.Main.immediate)

    val nativeImportViewModel: NativeImportViewModel by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        ViewModelProvider(
            this,
            ViewModelProvider.AndroidViewModelFactory.getInstance(this),
        )[NativeImportViewModel::class.java]
    }

    override fun onCreate() {
        super.onCreate()
        NativeImportNotificationController.ensureChannel(this)
        superviseNativeImport()
    }

    private fun superviseNativeImport() {
        val model = nativeImportViewModel
        applicationScope.launch {
            var lastServiceStart = 0L
            var lastPassiveSignature = ""
            var previousPhase = NativeImportPhase.IDLE
            while (isActive) {
                val state = model.state
                when {
                    state.busy -> {
                        val now = SystemClock.elapsedRealtime()
                        if (now - lastServiceStart >= 5_000L) {
                            runCatching { NativeImportNotificationController.start(this@LuoShuApplication) }
                            lastServiceStart = now
                        }
                        lastPassiveSignature = ""
                    }
                    state.phase != NativeImportPhase.IDLE -> {
                        val signature = "${state.phase}:${state.processed}:${state.message}"
                        if (signature != lastPassiveSignature) {
                            NativeImportNotificationController.notify(this@LuoShuApplication, state)
                            lastPassiveSignature = signature
                        }
                        lastServiceStart = 0L
                    }
                    previousPhase != NativeImportPhase.IDLE -> {
                        NativeImportNotificationController.cancel(this@LuoShuApplication)
                        lastPassiveSignature = ""
                        lastServiceStart = 0L
                    }
                }
                previousPhase = state.phase
                // 任务进度以文件为单位更新，不需要每秒轮询四次，降低常驻主线程唤醒。
                delay(500L)
            }
        }
    }

    override fun onTerminate() {
        applicationScope.cancel()
        viewModelStore.clear()
        super.onTerminate()
    }
}

@Composable
internal fun rememberNativeImportViewModel(): NativeImportViewModel {
    val application = LocalContext.current.applicationContext as LuoShuApplication
    return remember(application) { application.nativeImportViewModel }
}
