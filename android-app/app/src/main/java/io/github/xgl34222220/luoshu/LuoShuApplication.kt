package io.github.xgl34222220.luoshu

import android.app.Application
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.runtime.snapshotFlow
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.flow.distinctUntilChanged
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
            var foregroundServiceExpected = false
            var lastPassiveSignature = ""
            var previousPhase = NativeImportPhase.IDLE
            snapshotFlow { model.state }
                .distinctUntilChanged()
                .collect { state ->
                when {
                    state.busy -> {
                        if (!foregroundServiceExpected) {
                            foregroundServiceExpected = runCatching {
                                NativeImportNotificationController.start(this@LuoShuApplication)
                            }.isSuccess
                        }
                        lastPassiveSignature = ""
                    }
                    state.phase != NativeImportPhase.IDLE -> {
                        // A running service publishes the transition before it exits.
                        // Restored paused/terminal records have no service, so the
                        // application publishes them once.
                        if (!foregroundServiceExpected) {
                            val signature = "${state.phase}:${state.processed}:${state.message}"
                            if (signature != lastPassiveSignature) {
                                NativeImportNotificationController.notify(this@LuoShuApplication, state)
                                lastPassiveSignature = signature
                            }
                        }
                        foregroundServiceExpected = false
                    }
                    previousPhase != NativeImportPhase.IDLE -> {
                        NativeImportNotificationController.cancel(this@LuoShuApplication)
                        lastPassiveSignature = ""
                        foregroundServiceExpected = false
                    }
                }
                previousPhase = state.phase
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
