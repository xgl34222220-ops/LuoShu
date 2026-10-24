package io.github.xgl34222220.luoshu.globalfont;

import static org.junit.Assert.assertEquals;

import org.junit.Test;

/** The native companion looks this exact property up; renaming it silently breaks coexistence. */
public class ProcessMarkerTest {
    @Test
    public void markerNameIsStable() {
        assertEquals("luoshu.gfh.active", ModuleConfig.PROCESS_MARKER);
    }
}
