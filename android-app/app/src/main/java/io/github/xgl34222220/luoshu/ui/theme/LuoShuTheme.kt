package io.github.xgl34222220.luoshu.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.materialkolor.DynamicMaterialTheme
import com.materialkolor.PaletteStyle
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.LocalAppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

/**
 * Unified visual tokens shared by every LuoShu business screen.
 *
 * Business composables should consume these semantic values instead of inventing page-local
 * colors, spacing or corner radii. This keeps the Miuix and Material 3 skins on one information
 * architecture while still allowing their controls to look native to each style.
 */
@Immutable
data class LuoShuTokens(
    val pageBackground: Color,
    val surface: Color,
    val surfaceAlt: Color,
    val surfaceElevated: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val outline: Color,
    val success: Color,
    val warning: Color,
    val danger: Color,
    val pagePadding: Dp = 12.dp,
    val compactGap: Dp = 8.dp,
    val sectionGap: Dp = 12.dp,
    val smallRadius: Dp = 12.dp,
    val fieldRadius: Dp = 14.dp,
    val groupRadius: Dp = 18.dp,
    val dataRadius: Dp = 22.dp,
    val dockRadius: Dp = 32.dp,
    val sideSheetRadius: Dp = 32.dp,
)

val LocalLuoShuTokens = staticCompositionLocalOf {
    LuoShuTokens(
        pageBackground = Color(0xFFECEBFA),
        surface = Color(0xFFF8F7FD),
        surfaceAlt = Color(0xFFF2F0FA),
        surfaceElevated = Color.White,
        textPrimary = Color(0xFF171923),
        textSecondary = Color(0xFF666B7A),
        outline = Color(0x1F171923),
        success = Color(0xFF0AA45B),
        warning = Color(0xFFB87300),
        danger = Color(0xFFD83A3A),
    )
}

private val UnifiedMaterialShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(12.dp),
    medium = RoundedCornerShape(14.dp),
    large = RoundedCornerShape(18.dp),
    extraLarge = RoundedCornerShape(22.dp),
)

private val UnifiedMiuixShapes = Shapes(
    extraSmall = RoundedCornerShape(12.dp),
    small = RoundedCornerShape(14.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(22.dp),
    extraLarge = RoundedCornerShape(30.dp),
)

private val UnifiedTypography = Typography(
    displaySmall = TextStyle(fontSize = 30.sp, lineHeight = 36.sp, fontWeight = FontWeight.Bold),
    headlineLarge = TextStyle(fontSize = 28.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold),
    headlineMedium = TextStyle(fontSize = 26.sp, lineHeight = 32.sp, fontWeight = FontWeight.Bold),
    headlineSmall = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 18.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
    titleMedium = TextStyle(fontSize = 16.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
    titleSmall = TextStyle(fontSize = 15.sp, lineHeight = 21.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 14.sp, lineHeight = 21.sp, fontWeight = FontWeight.Normal),
    bodyMedium = TextStyle(fontSize = 13.sp, lineHeight = 19.sp, fontWeight = FontWeight.Normal),
    bodySmall = TextStyle(fontSize = 12.sp, lineHeight = 17.sp, fontWeight = FontWeight.Normal),
    labelLarge = TextStyle(fontSize = 13.sp, lineHeight = 18.sp, fontWeight = FontWeight.SemiBold),
    labelMedium = TextStyle(fontSize = 12.sp, lineHeight = 17.sp, fontWeight = FontWeight.Medium),
    labelSmall = TextStyle(fontSize = 10.sp, lineHeight = 14.sp, fontWeight = FontWeight.Medium),
)

@Immutable
data class MiuixTokens(
    val pageBackground: Color,
    val cardBackground: Color,
    val elevatedCardBackground: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val success: Color = Color(0xFF0AA45B),
    val warning: Color = Color(0xFFB87300),
)

val LocalMiuixTokens = staticCompositionLocalOf {
    MiuixTokens(
        pageBackground = Color(0xFFECEBFA),
        cardBackground = Color(0xFFF8F7FD),
        elevatedCardBackground = Color.White,
        textPrimary = Color(0xFF171923),
        textSecondary = Color(0xFF666B7A),
    )
}

@Composable
fun LuoShuTheme(settings: AppearanceSettings, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalAppearanceSettings provides settings) {
        when (settings.uiStyle) {
            UiStyle.MATERIAL -> LuoShuMaterialTheme(settings, content)
            UiStyle.MIUIX -> LuoShuMiuixTheme(settings, content)
        }
    }
}

@Composable
private fun LuoShuMaterialTheme(settings: AppearanceSettings, content: @Composable () -> Unit) {
    val dark = resolveDark(settings.themeMode)
    val pureBlack = dark && settings.amoledBlack
    DynamicMaterialTheme(
        seedColor = resolveSeedColor(settings),
        useDarkTheme = dark,
        withAmoled = pureBlack,
        style = settings.kolorStyle.toPaletteStyle(),
        shapes = UnifiedMaterialShapes,
        typography = UnifiedTypography,
        animate = true,
    ) {
        val scheme = MaterialTheme.colorScheme
        val tokens = LuoShuTokens(
            pageBackground = when {
                pureBlack -> Color.Black
                dark -> Color(0xFF11131A)
                else -> Color(0xFFECEBFA)
            },
            surface = when {
                pureBlack -> Color(0xFF0C0C0D)
                dark -> Color(0xFF1B1E28)
                else -> scheme.surfaceContainerLowest.copy(alpha = .98f)
            },
            surfaceAlt = when {
                pureBlack -> Color(0xFF171719)
                dark -> Color(0xFF252937)
                else -> scheme.surfaceContainerLow
            },
            surfaceElevated = when {
                pureBlack -> Color(0xFF171719)
                dark -> scheme.surfaceContainerHigh
                else -> scheme.surface
            },
            textPrimary = if (pureBlack) Color(0xFFF4F4F5) else scheme.onSurface,
            textSecondary = if (pureBlack) Color(0xFFB6B6BC) else scheme.onSurfaceVariant,
            outline = scheme.outlineVariant.copy(alpha = if (dark) .55f else .42f),
            success = Color(0xFF0AA45B),
            warning = Color(0xFFB87300),
            danger = Color(0xFFD83A3A),
        )
        CompositionLocalProvider(LocalLuoShuTokens provides tokens, content = content)
    }
}

@Composable
private fun LuoShuMiuixTheme(settings: AppearanceSettings, content: @Composable () -> Unit) {
    val dark = resolveDark(settings.themeMode)
    val pureBlack = dark && settings.amoledBlack
    DynamicMaterialTheme(
        seedColor = resolveSeedColor(settings),
        useDarkTheme = dark,
        withAmoled = pureBlack,
        style = settings.kolorStyle.toPaletteStyle(),
        shapes = UnifiedMiuixShapes,
        typography = UnifiedTypography,
        animate = true,
    ) {
        val scheme = MaterialTheme.colorScheme
        val page = when {
            pureBlack -> Color.Black
            dark -> Color(0xFF11131A)
            else -> Color(0xFFECEBFA)
        }
        val surface = when {
            pureBlack -> Color(0xFF0C0C0D)
            dark -> Color(0xFF1B1E28)
            else -> Color(0xFFF8F7FD)
        }
        val surfaceAlt = when {
            pureBlack -> Color(0xFF171719)
            dark -> Color(0xFF252937)
            else -> Color(0xFFF2F0FA)
        }
        val elevated = when {
            pureBlack -> Color(0xFF171719)
            dark -> scheme.surfaceContainerHigh
            else -> Color.White
        }
        val primaryText = when {
            pureBlack -> Color(0xFFF4F4F5)
            dark -> Color(0xFFF2F4F8)
            else -> Color(0xFF171923)
        }
        val secondaryText = when {
            pureBlack -> Color(0xFFB6B6BC)
            dark -> Color(0xFFB9BECA)
            else -> Color(0xFF666B7A)
        }
        val miuixTokens = MiuixTokens(
            pageBackground = page,
            cardBackground = surface,
            elevatedCardBackground = elevated,
            textPrimary = primaryText,
            textSecondary = secondaryText,
        )
        val unifiedTokens = LuoShuTokens(
            pageBackground = page,
            surface = surface,
            surfaceAlt = surfaceAlt,
            surfaceElevated = elevated,
            textPrimary = primaryText,
            textSecondary = secondaryText,
            outline = if (dark) Color.White.copy(alpha = .10f) else Color(0x1F171923),
            success = Color(0xFF0AA45B),
            warning = Color(0xFFB87300),
            danger = Color(0xFFD83A3A),
        )
        CompositionLocalProvider(
            LocalMiuixTokens provides miuixTokens,
            LocalLuoShuTokens provides unifiedTokens,
            content = content,
        )
    }
}

@Composable
private fun resolveSeedColor(settings: AppearanceSettings): Color {
    val resources = LocalResources.current
    return if (settings.monetEnabled && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        Color(resources.getColor(android.R.color.system_accent1_500, null))
    } else {
        Color(settings.seedArgb)
    }
}

@Composable
private fun resolveDark(mode: ThemeMode): Boolean = when (mode) {
    ThemeMode.SYSTEM -> isSystemInDarkTheme()
    ThemeMode.LIGHT -> false
    ThemeMode.DARK -> true
}

private fun KolorStyle.toPaletteStyle(): PaletteStyle = when (this) {
    KolorStyle.SOFT -> PaletteStyle.TonalSpot
    KolorStyle.VIBRANT -> PaletteStyle.Vibrant
    KolorStyle.NEUTRAL -> PaletteStyle.Neutral
}
