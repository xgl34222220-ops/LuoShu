package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/** Extra scroll range used only while the floating glass dock overlays page content. */
internal val LocalDockContentPadding = staticCompositionLocalOf<Dp> { 0.dp }
