package io.github.xgl34222220.luoshu.ui.studio

import android.view.Gravity
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.DarkMode
import androidx.compose.material.icons.rounded.LightMode
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.FontItem
import io.github.xgl34222220.luoshu.NativeFontPreview

@Composable
internal fun StudioSlotPreview(
    font: FontItem,
    text: String,
    axes: Map<String, Float>,
    modifier: Modifier = Modifier,
) {
    var darkPreview by remember(font.id) { mutableStateOf(false) }
    val lightBackground = Color(0xFFF0F4F9)
    val lightText = Color(0xFF1A1C1E)
    val darkBackground = Color(0xFF1A1C1E)
    val darkText = Color(0xFFF8FAFC)
    val background = if (darkPreview) darkBackground else lightBackground
    val foreground = if (darkPreview) darkText else lightText

    Surface(
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        color = background,
        contentColor = foreground,
    ) {
        Box {
            NativeFontPreview(
                font = font,
                text = text,
                axes = axes,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(84.dp)
                    .padding(start = 15.dp, end = 48.dp),
                textSizeSp = 25f,
                gravity = Gravity.CENTER,
                maxLines = 1,
                textColor = foreground,
            )
            Surface(
                modifier = Modifier
                    .align(Alignment.TopEnd)
                    .padding(7.dp),
                shape = RoundedCornerShape(12.dp),
                color = foreground.copy(alpha = .08f),
                contentColor = foreground,
            ) {
                IconButton(
                    onClick = { darkPreview = !darkPreview },
                    modifier = Modifier.size(34.dp),
                ) {
                    Icon(
                        if (darkPreview) Icons.Rounded.LightMode else Icons.Rounded.DarkMode,
                        contentDescription = if (darkPreview) "切换浅色预览" else "切换深色预览",
                        modifier = Modifier.size(17.dp),
                    )
                }
            }
        }
    }
}
