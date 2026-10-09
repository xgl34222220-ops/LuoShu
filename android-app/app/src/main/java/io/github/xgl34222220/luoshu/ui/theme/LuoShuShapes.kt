package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.runtime.Immutable
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.unit.Density
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.LayoutDirection
import androidx.compose.ui.unit.dp
import top.yukonga.miuix.kmp.squircle.addSquircleRect

/** One continuous outline for card fill, touch feedback and border, on every supported API. */
@Immutable
internal data class LuoShuSmoothShape(val cornerRadius: Dp = 24.dp) : Shape {
    override fun createOutline(size: Size, layoutDirection: LayoutDirection, density: Density): Outline =
        Outline.Generic(Path().apply {
            addSquircleRect(
                width = size.width,
                height = size.height,
                cornerRadius = with(density) { cornerRadius.toPx() },
            )
        })
}
