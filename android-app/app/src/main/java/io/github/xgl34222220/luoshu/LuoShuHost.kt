package io.github.xgl34222220.luoshu

import android.app.Activity
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.WindowInsetsSides
import androidx.compose.foundation.layout.consumeWindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.only
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.SideEffect
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalView
import androidx.core.view.WindowCompat
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme

// Legacy inventory marker: viewModel<NativeImportViewModel>() was replaced by the Application-scoped owner.
@Composable
internal fun LuoShuHost() {
    val model: LuoShuViewModel = viewModel()
    val features: Alpha15FeatureViewModel = viewModel()
    val appearanceViewModel: AppearanceViewModel = viewModel()
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()
    val lifecycleOwner = LocalLifecycleOwner.current

    DisposableEffect(lifecycleOwner, model) {
        val lifecycle = lifecycleOwner.lifecycle
        val observer = LifecycleEventObserver { _, _ ->
            model.setForeground(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED))
        }
        model.setForeground(lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED))
        lifecycle.addObserver(observer)
        onDispose {
            lifecycle.removeObserver(observer)
            model.setForeground(false)
        }
    }

    LuoShuTheme(appearance) {
        val pageBackground = if (appearance.uiStyle == UiStyle.MIUIX) {
            LocalMiuixTokens.current.pageBackground
        } else {
            MaterialTheme.colorScheme.background
        }
        val useDarkSystemBars = pageBackground.luminance() < .5f
        val context = LocalContext.current
        val view = LocalView.current
        val contentInsets = WindowInsets.safeDrawing.only(
            WindowInsetsSides.Top + WindowInsetsSides.Horizontal,
        )

        SideEffect {
            val window = (context as? Activity)?.window ?: return@SideEffect
            WindowCompat.getInsetsController(window, view).apply {
                isAppearanceLightStatusBars = !useDarkSystemBars
                isAppearanceLightNavigationBars = !useDarkSystemBars
            }
        }

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(pageBackground),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .windowInsetsPadding(contentInsets)
                    .consumeWindowInsets(contentInsets),
            ) {
                LuoShuAppShell(model, features, appearanceViewModel)
            }
        }
    }
}
