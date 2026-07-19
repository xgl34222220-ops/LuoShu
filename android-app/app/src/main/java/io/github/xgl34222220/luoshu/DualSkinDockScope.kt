package io.github.xgl34222220.luoshu

import androidx.compose.foundation.layout.RowScope
import androidx.compose.runtime.Composable
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.ui.appearance.LocalAppearanceSettings

/**
 * BoxWithConstraints and Row both use Compose DSL markers, so the inner Row
 * cannot read the outer maxWidth implicitly. Expose the actual dock content
 * width on RowScope to keep the five destinations evenly sized.
 */
internal val RowScope.maxWidth: Dp
    @Composable get() {
        val settings = LocalAppearanceSettings.current
        val screenWidth = LocalConfiguration.current.screenWidthDp.dp
        val horizontalInsets = if (settings.floatingDock) 44.dp else 12.dp
        return (screenWidth - horizontalInsets).coerceAtLeast(280.dp)
    }
