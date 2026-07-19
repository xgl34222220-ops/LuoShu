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
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.materialkolor.DynamicMaterialTheme
import com.materialkolor.PaletteStyle
import io.github.xgl34222220.luoshu.ui.appearance.AppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.KolorStyle
import io.github.xgl34222220.luoshu.ui.appearance.LocalAppearanceSettings
import io.github.xgl34222220.luoshu.ui.appearance.ThemeMode
import io.github.xgl34222220.luoshu.ui.appearance.UiStyle

private val MaterialShapes = Shapes(
    extraSmall = RoundedCornerShape(4.dp),
    small = RoundedCornerShape(8.dp),
    medium = RoundedCornerShape(12.dp),
    large = RoundedCornerShape(20.dp),
    extraLarge = RoundedCornerShape(32.dp),
)

private val MaterialTypography = Typography(
    displaySmall = TextStyle(fontSize = 38.sp, lineHeight = 43.sp, fontWeight = FontWeight.Black),
    headlineLarge = TextStyle(fontSize = 32.sp, lineHeight = 37.sp, fontWeight = FontWeight.Black),
    headlineMedium = TextStyle(fontSize = 26.sp, lineHeight = 31.sp, fontWeight = FontWeight.Bold),
    titleLarge = TextStyle(fontSize = 21.sp, lineHeight = 26.sp, fontWeight = FontWeight.Bold),
    titleMedium = TextStyle(fontSize = 17.sp, lineHeight = 22.sp, fontWeight = FontWeight.SemiBold),
    bodyLarge = TextStyle(fontSize = 16.sp, lineHeight = 23.sp),
    bodyMedium = TextStyle(fontSize = 14.sp, lineHeight = 20.sp),
    labelLarge = TextStyle(fontSize = 14.sp, fontWeight = FontWeight.Bold),
)

private val MiuixShapes = Shapes(
    extraSmall = RoundedCornerShape(10.dp),
    small = RoundedCornerShape(14.dp),
    medium = RoundedCornerShape(20.dp),
    large = RoundedCornerShape(28.dp),
    extraLarge = RoundedCornerShape(36.dp),
)

private val MiuixTypography = Typography(
    displaySmall = TextStyle(fontSize = 42.sp, lineHeight = 47.sp, fontWeight = FontWeight.Black),
    headlineLarge = TextStyle(fontSize = 34.sp, lineHeight = 39.sp, fontWeight = FontWeight.Black),
    headlineMedium = TextStyle(fontSize = 27.sp, lineHeight = 32.sp, fontWeight = FontWeight.Black),
    titleLarge = TextStyle(fontSize = 20.sp, lineHeight = 25.sp, fontWeight = FontWeight.Bold),
    titleMedium = TextStyle(fontSize = 16.sp, lineHeight = 21.sp, fontWeight = FontWeight.Bold),
    bodyMedium = TextStyle(fontSize = 13.sp, lineHeight = 18.sp),
    labelLarge = TextStyle(fontSize = 13.sp, fontWeight = FontWeight.Bold),
)

@Immutable
data class MiuixTokens(
    val pageBackground: Color,
    val cardBackground: Color,
    val elevatedCardBackground: Color,
    val textPrimary: Color,
    val textSecondary: Color,
    val success: Color = Color(0xFF27BE83),
    val warning: Color = Color(0xFFF0A532),
)

val LocalMiuixTokens = staticCompositionLocalOf {
    MiuixTokens(
        pageBackground = Color(0xFFF4F4F6),
        cardBackground = Color.White,
        elevatedCardBackground = Color.White,
        textPrimary = Color(0xFF16171B),
        textSecondary = Color(0xFF70727C),
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
    DynamicMaterialTheme(
        seedColor = resolveSeedColor(settings),
        useDarkTheme = resolveDark(settings.themeMode),
        withAmoled = settings.amoledBlack,
        style = settings.kolorStyle.toPaletteStyle(),
        shapes = MaterialShapes,
        typography = MaterialTypography,
        animate = true,
        content = content,
    )
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
        val scheme = MaterialTheme.colorScheme
        val tokens = MiuixTokens(
            pageBackground = when {
                pureBlack -> Color.Black
                dark -> Color(0xFF101114)
                else -> Color(0xFFF4F4F6)
            },
            cardBackground = when {
                pureBlack -> Color(0xFF080808)
                dark -> Color(0xFF1C1D21)
                else -> Color.White
            },
            elevatedCardBackground = when {
                pureBlack -> Color(0xFF111111)
                dark -> Color(0xFF24252A)
                else -> Color(0xFFFDFDFE)
            },
            textPrimary = scheme.onSurface,
            textSecondary = scheme.onSurfaceVariant,
        )
        CompositionLocalProvider(LocalMiuixTokens provides tokens, content = content)
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
