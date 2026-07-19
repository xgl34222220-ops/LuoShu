package io.github.xgl34222220.luoshu

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceViewModel
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle
import io.github.xgl34222220.luoshu.ui.theme.LocalMiuixTokens
import io.github.xgl34222220.luoshu.ui.theme.LuoShuTheme

@Composable
internal fun LuoShuHost() {
    val model: LuoShuViewModel = viewModel()
    val features: Alpha15FeatureViewModel = viewModel()
    val appearanceViewModel: AppearanceViewModel = viewModel()
    val appearance by appearanceViewModel.settings.collectAsStateWithLifecycle()

    LuoShuTheme(appearance) {
        val pageBackground = if (appearance.uiStyle == UiStyle.MIUIX) {
            LocalMiuixTokens.current.pageBackground
        } else {
            MaterialTheme.colorScheme.background
        }

        Box(
            modifier = Modifier
                .fillMaxSize()
                .background(pageBackground),
        ) {
            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .statusBarsPadding(),
            ) {
                LuoShuAppShell(model, features, appearanceViewModel)
            }
        }
    }
}
