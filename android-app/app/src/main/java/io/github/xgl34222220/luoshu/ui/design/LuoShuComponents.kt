package io.github.xgl34222220.luoshu.ui.design

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.defaultMinSize
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material.icons.rounded.ChevronRight
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

val LuoShuEnterEasing = CubicBezierEasing(.20f, .80f, .20f, 1f)
val LuoShuExitEasing = CubicBezierEasing(.40f, 0f, 1f, 1f)
val LuoShuStandardEasing = CubicBezierEasing(.20f, 0f, 0f, 1f)

@Composable
fun LuoShuPageHeader(
    title: String,
    subtitle: String? = null,
    modifier: Modifier = Modifier,
    centered: Boolean = false,
    leading: (@Composable () -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {},
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .padding(top = 8.dp, bottom = 6.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(Modifier.width(52.dp), contentAlignment = Alignment.CenterStart) {
            leading?.invoke()
        }
        Column(
            modifier = Modifier.weight(1f),
            horizontalAlignment = if (centered) Alignment.CenterHorizontally else Alignment.Start,
        ) {
            Text(
                text = title,
                color = tokens.textPrimary,
                style = MaterialTheme.typography.headlineMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!subtitle.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = subtitle,
                    color = tokens.textSecondary,
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        Row(
            modifier = Modifier.width(104.dp),
            horizontalArrangement = Arrangement.End,
            verticalAlignment = Alignment.CenterVertically,
            content = actions,
        )
    }
}

@Composable
fun LuoShuBackButton(onClick: () -> Unit, contentDescription: String = "返回") {
    LuoShuIconButton(
        icon = Icons.Rounded.ArrowBack,
        contentDescription = contentDescription,
        onClick = onClick,
    )
}

@Composable
fun LuoShuIconButton(
    icon: ImageVector,
    contentDescription: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    tint: Color = MaterialTheme.colorScheme.onSurface,
    containerColor: Color = LocalLuoShuTokens.current.surfaceElevated,
    content: (@Composable () -> Unit)? = null,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = modifier.size(48.dp),
        shape = RoundedCornerShape(tokens.fieldRadius),
        color = containerColor,
        border = androidx.compose.foundation.BorderStroke(1.dp, tokens.outline.copy(alpha = .55f)),
        shadowElevation = 2.dp,
    ) {
        IconButton(onClick = onClick, enabled = enabled) {
            if (content != null) content() else Icon(icon, contentDescription = contentDescription, tint = tint)
        }
    }
}

@Composable
fun LuoShuSectionTitle(
    title: String,
    modifier: Modifier = Modifier,
    action: (@Composable () -> Unit)? = null,
) {
    val tokens = LocalLuoShuTokens.current
    Row(
        modifier = modifier.fillMaxWidth().padding(start = 4.dp, top = 4.dp, end = 4.dp, bottom = 2.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            modifier = Modifier.weight(1f),
            color = tokens.textPrimary,
            style = MaterialTheme.typography.titleMedium,
        )
        action?.invoke()
    }
}

@Composable
fun LuoShuGroupCard(
    modifier: Modifier = Modifier,
    elevated: Boolean = false,
    contentPadding: Dp = 0.dp,
    content: @Composable () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    Card(
        modifier = modifier,
        shape = RoundedCornerShape(tokens.groupRadius),
        colors = CardDefaults.cardColors(containerColor = if (elevated) tokens.surfaceElevated else tokens.surface),
        elevation = CardDefaults.cardElevation(defaultElevation = if (elevated) 2.dp else 0.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, tokens.outline.copy(alpha = .42f)),
    ) {
        Box(Modifier.padding(contentPadding)) { content() }
    }
}

@Composable
fun LuoShuIconTile(
    icon: ImageVector,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.primary,
    containerColor: Color = MaterialTheme.colorScheme.primary.copy(alpha = .10f),
    size: Dp = 40.dp,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = modifier.size(size),
        shape = RoundedCornerShape(tokens.smallRadius),
        color = containerColor,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(21.dp))
        }
    }
}

@Composable
fun LuoShuSettingRow(
    icon: ImageVector,
    title: String,
    description: String? = null,
    modifier: Modifier = Modifier,
    enabled: Boolean = true,
    value: String? = null,
    showChevron: Boolean = false,
    onClick: (() -> Unit)? = null,
    trailing: (@Composable () -> Unit)? = null,
) {
    val tokens = LocalLuoShuTokens.current
    val interaction = remember { MutableInteractionSource() }
    Row(
        modifier = modifier
            .fillMaxWidth()
            .defaultMinSize(minHeight = 64.dp)
            .then(
                if (onClick != null) {
                    Modifier.clickable(
                        interactionSource = interaction,
                        indication = null,
                        enabled = enabled,
                        onClick = onClick,
                    )
                } else Modifier,
            )
            .padding(horizontal = 14.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        LuoShuIconTile(icon = icon, size = 38.dp)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                color = tokens.textPrimary.copy(alpha = if (enabled) 1f else .42f),
                style = MaterialTheme.typography.titleSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!description.isNullOrBlank()) {
                Spacer(Modifier.height(2.dp))
                Text(
                    text = description,
                    color = tokens.textSecondary.copy(alpha = if (enabled) 1f else .42f),
                    style = MaterialTheme.typography.bodySmall,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
        if (!value.isNullOrBlank()) {
            Spacer(Modifier.width(8.dp))
            Text(
                text = value,
                color = MaterialTheme.colorScheme.primary.copy(alpha = if (enabled) 1f else .42f),
                style = MaterialTheme.typography.labelMedium,
                maxLines = 1,
            )
        }
        trailing?.let {
            Spacer(Modifier.width(8.dp))
            it()
        }
        if (showChevron) {
            Spacer(Modifier.width(4.dp))
            Icon(
                Icons.Rounded.ChevronRight,
                contentDescription = null,
                tint = tokens.textSecondary.copy(alpha = if (enabled) .72f else .32f),
            )
        }
    }
}

@Composable
fun LuoShuDivider(modifier: Modifier = Modifier) {
    val tokens = LocalLuoShuTokens.current
    Box(modifier.fillMaxWidth().height(1.dp).background(tokens.outline.copy(alpha = .42f)))
}

@Composable
fun LuoShuMetricTile(
    title: String,
    value: String,
    modifier: Modifier = Modifier,
    icon: ImageVector? = null,
    statusColor: Color? = null,
) {
    val tokens = LocalLuoShuTokens.current
    Surface(
        modifier = modifier.defaultMinSize(minHeight = 84.dp),
        shape = RoundedCornerShape(tokens.fieldRadius),
        color = tokens.surfaceAlt,
        border = androidx.compose.foundation.BorderStroke(1.dp, tokens.outline.copy(alpha = .32f)),
    ) {
        Column(Modifier.padding(12.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (icon != null) {
                    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(6.dp))
                }
                Text(title, color = tokens.textSecondary, style = MaterialTheme.typography.bodySmall)
                if (statusColor != null) {
                    Spacer(Modifier.weight(1f))
                    Box(Modifier.size(7.dp).clip(RoundedCornerShape(99.dp)).background(statusColor))
                }
            }
            Spacer(Modifier.height(8.dp))
            Text(
                text = value,
                color = tokens.textPrimary,
                style = MaterialTheme.typography.titleMedium,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
        }
    }
}

@Composable
fun LuoShuSideSheet(
    visible: Boolean,
    onDismiss: () -> Unit,
    modifier: Modifier = Modifier,
    content: @Composable () -> Unit,
) {
    val tokens = LocalLuoShuTokens.current
    BoxWithConstraints(modifier.fillMaxSize()) {
        val sheetWidth = maxWidth * .94f
        AnimatedVisibility(
            visible = visible,
            enter = fadeIn(tween(180)),
            exit = fadeOut(tween(160)),
        ) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = .29f))
                    .clickable(
                        interactionSource = remember { MutableInteractionSource() },
                        indication = null,
                        onClick = onDismiss,
                    ),
            )
        }
        AnimatedVisibility(
            visible = visible,
            modifier = Modifier.align(Alignment.CenterEnd),
            enter = slideInHorizontally(
                animationSpec = tween(300, easing = LuoShuEnterEasing),
                initialOffsetX = { it },
            ) + fadeIn(tween(180)),
            exit = slideOutHorizontally(
                animationSpec = tween(220, easing = LuoShuExitEasing),
                targetOffsetX = { it },
            ) + fadeOut(tween(160)),
        ) {
            val shape = RoundedCornerShape(topStart = tokens.sideSheetRadius, bottomStart = tokens.sideSheetRadius)
            Box(
                modifier = Modifier
                    .width(sheetWidth)
                    .fillMaxHeight()
                    .shadow(24.dp, shape, clip = false)
                    .clip(shape)
                    .background(tokens.pageBackground)
                    .border(1.dp, tokens.outline.copy(alpha = .52f), shape),
            ) {
                content()
            }
        }
    }
}
