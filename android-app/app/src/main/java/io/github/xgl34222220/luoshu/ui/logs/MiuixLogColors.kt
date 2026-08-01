package io.github.xgl34222220.luoshu.ui.logs

import androidx.compose.ui.graphics.Color
import top.yukonga.miuix.kmp.theme.Colors

/**
 * Miuix exposes tertiary container colors but no scalar tertiary role.
 * Task-center status code previously used the Material role name, so map that
 * semantic status to the native Miuix secondary role without importing Material.
 */
internal val Colors.tertiary: Color
    get() = secondary
