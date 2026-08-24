package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp

/**
 * One visual scale for the active App UI. The slot stays fixed while opticalScale
 * compensates only the vector path, so selected/disabled/loading states never jump.
 */
internal object LuoShuIconTokens {
    // Material Studio already used a 56 dp refresh action while the shared tool action was 48 dp.
    // Use one 56 dp header touch/container contract in every style so paired actions align exactly.
    val HeaderContainer = 56.dp
    val HeaderGlyph = 22.dp
    val DockGlyph = 20.dp
    val SectionGlyph = 18.dp
    val ToolGlyph = 20.dp
    val LeadingGlyph = 20.dp
    val StatusGlyph = 22.dp
    val TrailingGlyph = 18.dp
    val ProgressGlyph = 22.dp
    val CompactProgress = 20.dp
}

@Composable
internal fun LuoShuGlyph(
    imageVector: ImageVector,
    contentDescription: String?,
    size: Dp,
    modifier: Modifier = Modifier,
    opticalScale: Float = 1f,
    tint: Color = Color.Unspecified,
) {
    val resolvedTint = if (tint == Color.Unspecified) LocalContentColor.current else tint
    Box(modifier = modifier.size(size), contentAlignment = Alignment.Center) {
        Icon(
            imageVector = imageVector,
            contentDescription = contentDescription,
            modifier = Modifier.fillMaxSize().scale(opticalScale),
            tint = resolvedTint,
        )
    }
}

@Composable
internal fun LuoShuHeaderAction(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    containerColor: Color,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    loading: Boolean = false,
    opticalScale: Float = 1f,
    contentColor: Color = Color.Unspecified,
) {
    val resolvedContentColor = if (contentColor == Color.Unspecified) {
        MaterialTheme.colorScheme.primary
    } else {
        contentColor
    }
    Surface(
        modifier = modifier.size(LuoShuIconTokens.HeaderContainer),
        shape = RoundedCornerShape(16.dp),
        color = containerColor,
        contentColor = resolvedContentColor,
        tonalElevation = 2.dp,
        shadowElevation = 3.dp,
    ) {
        IconButton(
            onClick = onClick,
            enabled = enabled,
            modifier = Modifier.fillMaxSize(),
        ) {
            if (loading) {
                CircularProgressIndicator(
                    modifier = Modifier.size(LuoShuIconTokens.ProgressGlyph),
                    strokeWidth = 2.dp,
                    color = resolvedContentColor,
                )
            } else {
                LuoShuGlyph(
                    imageVector = icon,
                    contentDescription = contentDescription,
                    size = LuoShuIconTokens.HeaderGlyph,
                    opticalScale = opticalScale,
                    tint = resolvedContentColor,
                )
            }
        }
    }
}