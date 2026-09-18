package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.foundation.layout.Box
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Shape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay

internal object LuoShuMotionTokens {
    const val Micro = 120
    const val Fast = 180
    const val Normal = 220
    const val Emphasized = 260
    const val LoadingRevealDelay = 160L
}

@Composable
internal fun LuoShuLoadingSkeleton(
    modifier: Modifier = Modifier,
    active: Boolean = true,
    shape: Shape = RoundedCornerShape(12.dp),
    revealDelayMs: Long = LuoShuMotionTokens.LoadingRevealDelay,
) {
    var revealed by remember(active) { mutableStateOf(false) }
    LaunchedEffect(active, revealDelayMs) {
        revealed = false
        if (active) {
            delay(revealDelayMs)
            revealed = true
        }
    }

    AnimatedVisibility(
        visible = active && revealed,
        enter = fadeIn(tween(LuoShuMotionTokens.Micro)),
        exit = fadeOut(tween(LuoShuMotionTokens.Micro)),
    ) {
        val shimmer = rememberInfiniteTransition(label = "luoshuSkeleton")
        val progress by shimmer.animateFloat(
            initialValue = 0f,
            targetValue = 1f,
            animationSpec = infiniteRepeatable(
                animation = tween(1400, easing = LinearEasing),
                repeatMode = RepeatMode.Restart,
            ),
            label = "luoshuSkeletonProgress",
        )
        val base = MaterialTheme.colorScheme.onSurface.copy(alpha = .055f)
        val highlight = MaterialTheme.colorScheme.onSurface.copy(alpha = .13f)
        Box(
            modifier = modifier
                .clip(shape)
                .drawBehind {
                    val band = size.width * .42f
                    val startX = -band + (size.width + band * 2f) * progress
                    drawRect(
                        Brush.linearGradient(
                            colors = listOf(base, highlight, base),
                            start = Offset(startX, 0f),
                            end = Offset(startX + band, size.height),
                        ),
                    )
                },
        )
    }
}
