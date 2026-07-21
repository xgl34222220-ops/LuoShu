package io.github.xgl34222220.luoshu.hook

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class QqFontCompatibilityTest {
    @Test
    fun qqHookRunsOnlyInMainUiProcess() {
        assertTrue(isQqUiProcess("com.tencent.mobileqq", "com.tencent.mobileqq"))
        assertTrue(isQqUiProcess("com.tencent.tim", "com.tencent.tim"))
        assertFalse(isQqUiProcess("com.tencent.mobileqq", "com.tencent.mobileqq:MSF"))
        assertFalse(isQqUiProcess("com.android.vending", "com.android.vending"))
    }

    @Test
    fun hyperOsDetectionUsesRomPropertiesAndBrandFallback() {
        assertTrue(isHyperOsFamily("Xiaomi", "Redmi", null, null))
        assertTrue(isHyperOsFamily("unknown", "unknown", "OS3.0", null))
        assertFalse(isHyperOsFamily("OnePlus", "OnePlus", null, null))
    }

    @Test
    fun iconAndEmojiTypefacesStayProtected() {
        assertTrue(shouldPreserveQqTypeface("\uE8B6", null))
        assertTrue(shouldPreserveQqTypeface("🙂", "NotoColorEmoji"))
        assertTrue(shouldPreserveQqTypeface("icon", "Material Symbols Rounded"))
        assertFalse(shouldPreserveQqTypeface("群通知", "sans-serif"))
    }

    @Test
    fun ordinarySystemFamiliesCanBeUnified() {
        assertTrue(isReplaceableQqFamily(null))
        assertTrue(isReplaceableQqFamily("sans-serif-medium"))
        assertTrue(isReplaceableQqFamily("MiSansVF"))
        assertFalse(isReplaceableQqFamily("MaterialIcons"))
        assertFalse(isReplaceableQqFamily("RobotoMono-Regular"))
    }

    @Test
    fun compactLabelDetectionDoesNotTouchNormalTextOrEditors() {
        assertTrue(isCompactQqLabelCandidate(11f, 22f, 1, 8, editable = false))
        assertFalse(isCompactQqLabelCandidate(17f, 24f, 1, 8, editable = false))
        assertFalse(isCompactQqLabelCandidate(11f, 48f, 1, 8, editable = false))
        assertFalse(isCompactQqLabelCandidate(11f, 22f, 2, 8, editable = false))
        assertFalse(isCompactQqLabelCandidate(11f, 22f, 1, 8, editable = true))
    }

    @Test
    fun labelTextShrinksOnlyWhenMetricsActuallyClip() {
        assertNull(fittedQqLabelTextSizePx(28f, 30, 28))
        val target = fittedQqLabelTextSizePx(28f, 22, 28)
        assertEquals(23.52f, target ?: 0f, 0.05f)
    }
}
