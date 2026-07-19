package io.github.xgl34222220.luoshu

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.viewmodel.compose.viewModel
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceViewModel

@Composable
internal fun LuoShuHost() {
    val model: LuoShuViewModel = viewModel()
    val features: Alpha15FeatureViewModel = viewModel()
    val appearance: AppearanceViewModel = viewModel()
    Box(Modifier.fillMaxSize()) {
        LuoShuDualSkinApp(model, features, appearance)
        NativeImportOverlay(
            viewModel = model,
            modifier = Modifier
                .align(Alignment.BottomEnd)
                .navigationBarsPadding()
                .padding(end = 18.dp, bottom = 98.dp),
        )
    }
}
