package io.github.xgl34222220.luoshu.ui.design

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.core.CubicBezierEasing
import androidx.compose.animation.core.tween
import androidx.compose.animation.fadeIn
import androidx.compose.animation.fadeOut
import androidx.compose.animation.slideInHorizontally
import androidx.compose.animation.slideOutHorizontally
import androidx.compose.foundation.BorderStroke
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
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.weight
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import io.github.xgl34222220.luoshu.ui.theme.LocalLuoShuTokens

val LuoShuEnterEasing = CubicBezierEasing(.20f, .80f, .20f, 1f)
val LuoShuExitEasing = CubicBezierEasing(.40f, 0f, 1f, 1f)
val LuoShuStandardEasing = CubicBezierEasing(.20f, 0f, 0f, 1f)

/**
 * One header system for every page.
 *
 * Action containers are always 48 dp. A centred title is laid out independently from the
 * left/right action count so one page can never shift simply because it has two actions.
 */
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
    val titleBlock: @Composable () -> Unit = {
        Column(horizontalAlignment = if (centered) Alignment.CenterHorizontally else Alignment.Start) {
            Text(
                text = title,
                color = tokens.textPrimary,
                style = MaterialTheme.typography.headlineLarge,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!subtitle.isNullOrBlank()) {
                Spacer(Modifier.height(1.dp))
                Text(
                    text = subtitle,
                    color = tokens.textSecondary,
                    style = MaterialTheme.typography.bodyMedium,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis,
                )
            }
        }
    }

    if (centered) {
        Box(
            modifier = modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .heightIn(min = 72.dp)
                .padding(vertical = 5.dp),
        ) {
            Box(Modifier.align(Alignment.Center), contentAlignment = Alignment.Center) { titleBlock() }
            if (leading != null) {
                Box(Modifier.align(Alignment.CenterStart), contentAlignment = Alignment.CenterStart) { leading() }
            }
            Row(
                modifier = Modifier.align(Alignment.CenterEnd),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                content = actions,
            )
        }
    } else {
        Row(
            modifier = modifier
                .fillMaxWidth()
                .statusBarsPadding()
                .heightIn(min = 72.dp)
                .padding(vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            if (leading != null) {
                Box(Modifier.size(48.dp), contentAlignment = Alignment.CenterStart) { leading() }
                Spacer(Modifier.width(8.dp))
            }
            Box(Modifier.weight(1f), contentAlignment = Alignment.CenterStart) { titleBlock() }
            Row(
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically,
                content = actions,
            )
        }
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

/** One and only top-level icon button specification. */
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
        shape = RoundedCornerShape(16.dp),
        color = containerColor,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .30f)),
        shadowElevation = 1.dp,
    ) {
        IconButton(onClick = onClick, enabled = enabled) {
            if (content != null) {
                content()
            } else {
                Icon(
                    imageVector = icon,
                    contentDescription = contentDescription,
                    tint = tint.copy(alpha = if (enabled) 1f else .38f),
                    modifier = Modifier.size(22.dp),
                )
            }
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
        modifier = modifier
            .fillMaxWidth()
            .padding(start = 4.dp, top = 8.dp, end = 4.dp, bottom = 3.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            text = title,
            modifier = Modifier.weight(1f),
            color = tokens.textPrimary,
            style = MaterialTheme.typography.titleLarge,
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
        elevation = CardDefaults.cardElevation(defaultElevation = if (elevated) 1.dp else 0.dp),
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .24f)),
    ) {
        Box(Modifier.padding(contentPadding)) { content() }
    }
}

@Composable
fun LuoShuIconTile(
    icon: ImageVector,
    modifier: Modifier = Modifier,
    tint: Color = MaterialTheme.colorScheme.primary,
    containerColor: Color = MaterialTheme.colorScheme.primary.copy(alpha = .09f),
    size: Dp = 34.dp,
) {
    Surface(
        modifier = modifier.size(size),
        shape = RoundedCornerShape(11.dp),
        color = containerColor,
    ) {
        Box(contentAlignment = Alignment.Center) {
            Icon(icon, contentDescription = null, tint = tint, modifier = Modifier.size(18.dp))
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
            .defaultMinSize(minHeight = 56.dp)
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
            .padding(horizontal = 12.dp, vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        LuoShuIconTile(icon = icon)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f)) {
            Text(
                text = title,
                color = tokens.textPrimary.copy(alpha = if (enabled) 1f else .42f),
                style = MaterialTheme.typography.titleSmall,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis,
            )
            if (!description.isNullOrBlank()) {
                Spacer(Modifier.height(1.dp))
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
                overflow = TextOverflow.Ellipsis,
            )
        }
        trailing?.let {
            Spacer(Modifier.width(8.dp))
            it()
        }
        if (showChevron) {
            Spacer(Modifier.width(2.dp))
            Icon(
                Icons.Rounded.ChevronRight,
                contentDescription = null,
                tint = tokens.textSecondary.copy(alpha = if (enabled) .66f else .28f),
                modifier = Modifier.size(20.dp),
            )
        }
    }
}

@Composable
fun LuoShuDivider(modifier: Modifier = Modifier) {
    val tokens = LocalLuoShuTokens.current
    Box(modifier.fillMaxWidth().height(1.dp).background(tokens.outline.copy(alpha = .28f)))
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
        modifier = modifier.defaultMinSize(minHeight = 68.dp),
        shape = RoundedCornerShape(tokens.fieldRadius),
        color = tokens.surfaceAlt,
        border = BorderStroke(1.dp, tokens.outline.copy(alpha = .20f)),
    ) {
        Column(Modifier.padding(horizontal = 11.dp, vertical = 9.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                if (icon != null) {
                    Icon(icon, contentDescription = null, tint = MaterialTheme.colorScheme.primary, modifier = Modifier.size(17.dp))
                    Spacer(Modifier.width(5.dp))
                }
                Text(title, color = tokens.textSecondary, style = MaterialTheme.typography.bodySmall)
                if (statusColor != null) {
                    Spacer(Modifier.weight(1f))
                    Box(Modifier.size(7.dp).clip(RoundedCornerShape(99.dp)).background(statusColor))
                }
            }
            Spacer(Modifier.height(5.dp))
            Text(
                text = value,
                color = tokens.textPrimary,
                style = MaterialTheme.typography.titleSmall,
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
        val sheetWidth = maxWidth * .92f
        AnimatedVisibility(
            visible = visible,
            enter = fadeIn(tween(160)),
            exit = fadeOut(tween(140)),
        ) {
            Box(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = .22f))
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
                animationSpec = tween(280, easing = LuoShuEnterEasing),
                initialOffsetX = { it },
            ) + fadeIn(tween(150)),
            exit = slideOutHorizontally(
                animationSpec = tween(210, easing = LuoShuExitEasing),
                targetOffsetX = { it },
            ) + fadeOut(tween(140)),
        ) {
            val shape = RoundedCornerShape(topStart = tokens.sideSheetRadius, bottomStart = tokens.sideSheetRadius)
            Box(
                modifier = Modifier
                    .width(sheetWidth)
                    .fillMaxHeight()
                    .shadow(12.dp, shape, clip = false)
                    .clip(shape)
                    .background(tokens.pageBackground)
                    .border(1.dp, tokens.outline.copy(alpha = .34f), shape),
            ) {
                content()
            }
        }
    }
}
