package io.github.xgl34222220.luoshu.ui.theme

import android.os.Build
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.LocalContentColor
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.Immutable
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.lerp
import androidx.compose.ui.platform.LocalResources
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.sp
import com.materialkolor.DynamicMaterialTheme
import com.materialkolor.PaletteStyle
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.LocalAppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode

private val MiuixShapes = Shapes(
    extraSmall = RoundedCornerShape(7.dp),
    small = RoundedCornerShape(11.dp),
    medium = RoundedCornerShape(18.dp),
    large = RoundedCornerShape(24.dp),
    extraLarge = RoundedCornerShape(30.dp),
)

private val MiuixTypography = Typography(
    displaySmall = TextStyle(fontSize = 34.sp, lineHeight = 39.sp, fontWeight = FontWeight.Bold),
    headlineLarge = TextStyle(fontSize = 30.sp, lineHeight = 38.sp, fontWeight = FontWeight.Bold),
    headlineMedium = TextStyle(fontSize = 26.sp, lineHeight = 34.sp, fontWeight = FontWeight.Bold),
    headlineSmall = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 22.sp, lineHeight = 28.sp, fontWeight = FontWeight.Bold),
    titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 24.sp, fontWeight = FontWeight.SemiBold),
    titleSmall = TextStyle(fontSize = 15.sp, lineHeight = 21.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 15.sp, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 21.sp),
    bodySmall = TextStyle(fontSize = 12.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Bold),
    labelSmall = TextStyle(fontSize = 11.sp, lineHeight = 16.sp, fontWeight = FontWeight.Medium, letterSpacing = .2.sp),
)

@Immutable
data class MiuixTokens(
    val pageBackground: Color,
    val cardBackground: Color,
    val elevatedCardBackground: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val cardOutline: Color = Color(0xFFE3E2DD),
    val glassEnabled: Boolean = false,
    val glassDialogColor: Color = cardBackground,
    val glassHighlight: Color = Color.Transparent,
    val glassOutlineBrush: Brush = Brush.linearGradient(listOf(cardOutline, cardOutline)),
    val cardShadowElevation: Dp = 0.dp,
    val insetBackground: Color = elevatedCardBackground,
    val insetOutline: Color = cardOutline,
    val success: Color = Color(0xFF27BE83),
    val warning: Color = Color(0xFFF0A532),
) {
    val glassCardColor: Color
        get() = cardBackground
}

val LocalMiuixTokens = staticCompositionLocalOf {
    MiuixTokens(
        pageBackground = Color(LuoShuGlassPalette.LightBackground),
        cardBackground = Color.White,
        elevatedCardBackground = Color.White,
        textPrimary = Color(0xFF16171B),
        textSecondary = Color(0xFF70727C),
    )
}

@Composable
fun LuoShuTheme(settings: AppearanceSettings, content: @Composable () -> Unit) {
    CompositionLocalProvider(LocalAppearanceSettings provides settings) {
        LuoShuMiuixTheme(settings, content)
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
        shapes = MiuixShapes,
        typography = MiuixTypography,
        animate = true,
    ) {
        // Keep large error surfaces quiet in both modes while retaining
        // readable error text and icons across every shared screen.
        val scheme = MaterialTheme.colorScheme
        val backdrop = when {
            pureBlack -> Color.Black
            dark -> Color(LuoShuGlassPalette.DarkBackground)
            else -> Color(LuoShuGlassPalette.LightBackground)
        }
        val surface = if (dark) Color(0xFF222A3B) else Color(0xFFF8FAFF)
        fun materialSurface(alpha: Float) = surface.copy(alpha = if (settings.glassEnabled) alpha else 1f)
        MaterialTheme(
            colorScheme = scheme.copy(
                background = backdrop,
                surface = materialSurface(.88f),
                surfaceContainerLowest = materialSurface(.78f),
                surfaceContainerLow = materialSurface(.84f),
                surfaceContainer = materialSurface(.89f),
                surfaceContainerHigh = materialSurface(.94f),
                surfaceContainerHighest = materialSurface(.97f),
                error = if (dark) Color(0xFFE9ABA7) else Color(0xFFA64A4A),
                onError = if (dark) Color(0xFF3D1F1D) else Color.White,
                errorContainer = (if (dark) Color(0xFF342627) else Color(0xFFF4E9E7)).copy(
                    alpha = if (settings.glassEnabled) .94f else 1f,
                ),
                onErrorContainer = if (dark) Color(0xFFF1D4D1) else Color(0xFF633734),
            ),
        ) {
            ProvideMiuixTokens(settings, content)
        }
    }
}

/** Shared screens use the same resolved MIUIx palette. */
@Composable
private fun ProvideMiuixTokens(settings: AppearanceSettings, content: @Composable () -> Unit) {
    val dark = resolveDark(settings.themeMode)
    val pureBlack = dark && settings.amoledBlack
    val scheme = MaterialTheme.colorScheme
    val glass = settings.glassEnabled
    val lightFill = Color(0xFFF8FAFF)
    val darkFill = if (pureBlack) Color(0xFF181C26) else Color(0xFF222A3B)
    val cardOutline = if (glass) {
        Color.White.copy(alpha = if (dark) .18f else .58f)
    } else {
        scheme.onSurface.copy(alpha = if (dark) .10f else .07f)
    }
    val tokens = MiuixTokens(
        pageBackground = when {
            pureBlack -> Color.Black
            dark -> Color(LuoShuGlassPalette.DarkBackground)
            else -> Color(LuoShuGlassPalette.LightBackground)
        },
        cardBackground = when {
            glass && dark -> darkFill.copy(alpha = .80f)
            glass -> lightFill.copy(alpha = .82f)
            dark -> darkFill
            else -> lightFill
        },
        elevatedCardBackground = when {
            glass && dark -> Color(0xFF35405A).copy(alpha = .78f)
            glass -> Color.White.copy(alpha = .78f)
            dark -> Color(0xFF30384A)
            else -> lerp(lightFill, scheme.primaryContainer, .06f)
        },
        textPrimary = scheme.onSurface,
        textSecondary = scheme.onSurfaceVariant,
        cardOutline = cardOutline,
        glassEnabled = glass,
        glassDialogColor = when {
            glass && dark -> Color(0xFF1B2333).copy(alpha = .95f)
            glass -> lightFill.copy(alpha = .94f)
            dark -> darkFill
            else -> lightFill
        },
        glassHighlight = if (glass) Color.White.copy(alpha = if (dark) .045f else .14f) else Color.Transparent,
        glassOutlineBrush = Brush.linearGradient(
            if (glass) {
                listOf(
                    Color.White.copy(alpha = if (dark) .22f else .64f),
                    Color.White.copy(alpha = if (dark) .065f else .22f),
                    Color(LuoShuGlassPalette.BlueGlow).copy(alpha = if (dark) .18f else .14f),
                )
            } else listOf(cardOutline, cardOutline),
        ),
        // One quiet edge separates cards; inset content does not stack another shadow.
        cardShadowElevation = if (glass) 1.dp else 0.dp,
        insetBackground = when {
            glass && dark -> Color(0xFF343F55).copy(alpha = .60f)
            glass -> Color(0xFFEEF2FA).copy(alpha = .84f)
            dark -> Color(0xFF303A4E)
            else -> Color(0xFFEEF2FA)
        },
        insetOutline = scheme.onSurface.copy(alpha = if (dark) .08f else .045f),
        success = if (dark) Color(0xFF69D9AD) else Color(0xFF187B58),
        warning = if (dark) Color(0xFFF3C378) else Color(0xFF956319),
    )
    CompositionLocalProvider(
        LocalMiuixTokens provides tokens,
        // Custom translucent fills are not exact ColorScheme surface roles.
        // Their contentColorFor fallback must follow our resolved theme too.
        LocalContentColor provides tokens.textPrimary,
        content = content,
    )
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
