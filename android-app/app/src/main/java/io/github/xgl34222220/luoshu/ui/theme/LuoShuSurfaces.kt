package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Outline
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.Shape
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.graphics.drawscope.clipPath
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

/** A cached sheen below the surface fill; text and touch feedback remain undimmed. */
@Composable
internal fun Modifier.luoShuGlassHighlight(
    shape: Shape = LuoShuSmoothShape(24.dp),
): Modifier {
    val tokens = LocalMiuixTokens.current
    if (!tokens.glassEnabled) return this
    val highlight = tokens.glassHighlight
    return drawWithCache {
        val outline = shape.createOutline(size, layoutDirection, this)
        val path = Path().apply {
            when (outline) {
                is Outline.Generic -> addPath(outline.path)
                is Outline.Rounded -> addRoundRect(outline.roundRect)
                is Outline.Rectangle -> addRect(outline.rect)
            }
        }
        val sheen = Brush.verticalGradient(listOf(highlight, Color.Transparent))
        onDrawBehind {
            clipPath(path) { drawRect(sheen) }
        }
    }
}

/** A quiet inner layer for samples and summaries, without another shadow or blur pass. */
@Composable
internal fun LuoShuInsetPanel(
    modifier: Modifier = Modifier,
    content: @Composable ColumnScope.() -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = LuoShuSmoothShape(18.dp),
        color = tokens.insetBackground,
        contentColor = tokens.textPrimary,
        border = BorderStroke(1.dp, tokens.insetOutline),
        tonalElevation = 0.dp,
        shadowElevation = 0.dp,
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            content = content,
        )
    }
}

/** A shared translucent material without a blur pass or frame producer for every card. */
@Composable
internal fun LuoShuSurfaceCard(
    modifier: Modifier = Modifier,
    emphasized: Boolean = false,
    content: @Composable ColumnScope.() -> Unit,
) {
    val tokens = LocalMiuixTokens.current
    val shape = LuoShuSmoothShape(24.dp)
    Surface(
        modifier = modifier.fillMaxWidth().luoShuGlassHighlight(shape),
        shape = shape,
        color = if (emphasized) {
            lerp(tokens.cardBackground, MaterialTheme.colorScheme.primaryContainer.copy(alpha = tokens.cardBackground.alpha), .12f)
        } else tokens.cardBackground,
        contentColor = tokens.textPrimary,
        shadowElevation = tokens.cardShadowElevation,
        border = BorderStroke(1.dp, tokens.glassOutlineBrush),
    ) {
        Column(
            modifier = Modifier.padding(20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
            content = content,
        )
    }
}

@Composable
internal fun LuoShuSectionHeading(
    title: String,
    subtitle: String? = null,
    modifier: Modifier = Modifier,
    action: @Composable () -> Unit = {},
) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = modifier.fillMaxWidth().padding(horizontal = 2.dp, vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(3.dp)) {
            Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = tokens.textPrimary)
            subtitle?.takeIf { it.isNotBlank() }?.let {
                Text(it, style = MaterialTheme.typography.bodySmall, color = tokens.textSecondary)
            }
        }
        action()
    }
}
