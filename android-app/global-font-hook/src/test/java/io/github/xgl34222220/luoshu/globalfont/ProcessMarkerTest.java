package io.github.xgl34222220.luoshu.globalfont;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

/** The native companion looks this exact property up; renaming it silently breaks coexistence. */
public class ProcessMarkerTest {
    @Test
    public void markerNameIsStable() {
        assertEquals("luoshu.gfh.active", ModuleConfig.PROCESS_MARKER);
    }

    /** Module preferences live in the LuoShu App that carries the module (debug test builds: .debug). */
    @Test
    public void moduleIsTheLuoShuApp() {
        assertEquals("io.github.xgl34222220.luoshu.debug", ModuleConfig.MODULE_PACKAGE);
        assertTrue(ModuleConfig.isLuoShuApp("io.github.xgl34222220.luoshu"));
        assertTrue(ModuleConfig.isLuoShuApp("io.github.xgl34222220.luoshu.debug"));
        assertFalse(ModuleConfig.isLuoShuApp(ModuleConfig.LEGACY_COMPANION_PACKAGE));
        assertFalse(ModuleConfig.isLuoShuApp("com.tencent.mm"));
    }

    /** Old companion still enabled and already hooked this process: the built-in copy skips. */
    @Test
    public void markerSetByAnotherCopyMeansSkip() {
        String before = System.getProperty(ModuleConfig.PROCESS_MARKER);
        try {
            System.clearProperty(ModuleConfig.PROCESS_MARKER);
            assertFalse(ModuleConfig.alreadyReplaced());
            System.setProperty(ModuleConfig.PROCESS_MARKER, "1");
            assertTrue(ModuleConfig.alreadyReplaced());
        } finally {
            if (before == null) System.clearProperty(ModuleConfig.PROCESS_MARKER);
            else System.setProperty(ModuleConfig.PROCESS_MARKER, before);
        }
    }

    /** Without LSPosed the App's own status query reports inactive (the self hook flips it). */
    @Test
    public void selfStatusDefaultsToInactive() {
        assertFalse(ModuleStatus.isModuleActive());
    }
}
