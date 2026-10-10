package io.github.xgl34222220.luoshu.ui.launch

import android.provider.Settings
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.drawscope.drawIntoCanvas
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.nativeCanvas
import androidx.compose.ui.platform.LocalContext

/**
 * Full-screen diffuse/glass launch shell drawn ABOVE the already composed home.
 *
 * Its first frame equals the native preparation View (API 31+) and the API 28–30
 * starting window. It drifts, sweeps one shimmer across the glass, then crossfades
 * away within [LuoShuLaunchShellTimeline.TOTAL_MS]. Home composition, first-frame
 * delivery and permission release are never gated on it. With animator scale 0 it
 * stays static and leaves as soon as the first home frame was committed.
 */
@Composable
internal fun LuoShuLaunchShell(
    textAlreadyVisible: Boolean,
    contentReady: Boolean,
    onFinished: () -> Unit,
) {
    val context = LocalContext.current
    val artwork = remember { LuoShuLaunchArtwork.obtain(context) }
    val finish by rememberUpdatedState(onFinished)
    val motionEnabled = remember {
        Settings.Global.getFloat(context.contentResolver, Settings.Global.ANIMATOR_DURATION_SCALE, 1f) > 0f
    }
    val clock = remember { Animatable(0f) }
    if (motionEnabled) {
        LaunchedEffect(Unit) {
            // The Compose frame clock applies the system animator duration scale.
            clock.animateTo(
                LuoShuLaunchShellTimeline.TOTAL_MS,
                tween(LuoShuLaunchShellTimeline.TOTAL_MS.toInt(), easing = LinearEasing),
            )
            finish()
        }
    } else {
        LaunchedEffect(contentReady) { if (contentReady) finish() }
    }
    DisposableEffect(Unit) { onDispose { LuoShuLaunchArtwork.release() } }
    Canvas(
        Modifier
            .fillMaxSize()
            .graphicsLayer { alpha = LuoShuLaunchShellTimeline.shellAlpha(clock.value) },
    ) {
        val frame = LuoShuLaunchShellTimeline.frameAt(clock.value, textAlreadyVisible || !motionEnabled)
        drawIntoCanvas { canvas ->
            artwork.draw(canvas.nativeCanvas, size.width.toInt(), size.height.toInt(), frame)
        }
    }
}
