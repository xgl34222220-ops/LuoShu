package io.github.xgl34222220.luoshu.ui.studio

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.AutoAwesome
import androidx.compose.material.icons.rounded.Description
import androidx.compose.material.icons.rounded.ListAlt
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

@Composable
internal fun StudioToolLauncherRow(
    style: UiStyle,
    enabled: Boolean,
    onPreview: () -> Unit,
    onProfile: () -> Unit,
    onGlyphs: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Row(modifier = modifier, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        StudioToolButton(style, "预览", Icons.Rounded.AutoAwesome, enabled, onPreview)
        StudioToolButton(style, "方案", Icons.Rounded.Description, enabled, onProfile)
        StudioToolButton(style, "字形", Icons.Rounded.ListAlt, enabled, onGlyphs)
    }
}

@Composable
private fun StudioToolButton(
    style: UiStyle,
    label: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Surface(
        onClick = onClick,
        enabled = enabled,
        shape = RoundedCornerShape(if (style == UiStyle.MIUIX) 21.dp else 18.dp),
        color = if (enabled) MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.surfaceVariant,
        contentColor = if (enabled) MaterialTheme.colorScheme.onPrimary else MaterialTheme.colorScheme.onSurfaceVariant,
        shadowElevation = if (enabled) 8.dp else 0.dp,
    ) {
        Row(
            modifier = Modifier.padding(horizontal = 12.dp, vertical = 11.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Icon(icon, contentDescription = null, modifier = Modifier.size(18.dp))
            Spacer(Modifier.size(5.dp))
            Text(label, fontSize = 10.sp, fontWeight = FontWeight.Black)
        }
    }
}
