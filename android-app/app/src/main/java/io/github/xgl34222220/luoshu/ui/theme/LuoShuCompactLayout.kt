package io.github.xgl34222220.luoshu.ui.theme

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.ArrowBack
import androidx.compose.material3.IconButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/**
 * Compact top bars shared by the active LuoShu screens.
 *
 * The title is placed independently from the action slots, so one or two actions never
 * push it away from the visual center. This follows the quiet, dense hierarchy used by
 * the UI reference: navigation chrome is light while content groups carry the structure.
 */
@Composable
internal fun LuoShuTopBar(
    title: String,
    modifier: Modifier = Modifier,
    actions: @Composable () -> Unit = {},
) {
    val tokens = LocalMiuixTokens.current
    Box(
        modifier = modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .height(52.dp),
    ) {
        Text(
            text = title,
            modifier = Modifier.align(Alignment.Center),
            color = tokens.textPrimary,
            fontSize = 22.sp,
            lineHeight = 27.sp,
            fontWeight = FontWeight.Black,
        )
        Row(
            modifier = Modifier.align(Alignment.CenterEnd),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.End,
        ) {
            actions()
        }
    }
}

@Composable
internal fun LuoShuDetailBar(
    title: String,
    onBack: () -> Unit,
    modifier: Modifier = Modifier,
    actions: @Composable () -> Unit = {},
) {
    val tokens = LocalMiuixTokens.current
    Row(
        modifier = modifier
            .fillMaxWidth()
            .statusBarsPadding()
            .height(62.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        IconButton(onClick = onBack) {
            LuoShuGlyph(
                imageVector = Icons.Rounded.ArrowBack,
                contentDescription = "返回",
                size = LuoShuIconTokens.ToolGlyph,
                tint = tokens.textPrimary,
            )
        }
        Text(
            text = title,
            modifier = Modifier.weight(1f).padding(start = 2.dp),
            color = tokens.textPrimary,
            fontSize = 26.sp,
            lineHeight = 31.sp,
            fontWeight = FontWeight.Black,
            maxLines = 1,
        )
        Row(
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.End,
        ) {
            actions()
        }
    }
}
