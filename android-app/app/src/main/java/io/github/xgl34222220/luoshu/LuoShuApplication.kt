package io.github.xgl34222220.luoshu

import android.app.Application
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner

internal class LuoShuApplication : Application(), ViewModelStoreOwner {
    override val viewModelStore: ViewModelStore = ViewModelStore()

    val nativeImportViewModel: NativeImportViewModel by lazy(LazyThreadSafetyMode.SYNCHRONIZED) {
        ViewModelProvider(
            this,
            ViewModelProvider.AndroidViewModelFactory.getInstance(this),
        )[NativeImportViewModel::class.java]
    }

    override fun onTerminate() {
        viewModelStore.clear()
        super.onTerminate()
    }
}

@Composable
internal fun rememberNativeImportViewModel(): NativeImportViewModel {
    val application = LocalContext.current.applicationContext as LuoShuApplication
    return remember(application) { application.nativeImportViewModel }
}
