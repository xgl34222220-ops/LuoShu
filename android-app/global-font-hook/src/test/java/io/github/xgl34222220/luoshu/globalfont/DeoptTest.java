package io.github.xgl34222220.luoshu.globalfont;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertNotNull;
import static org.junit.Assert.assertNull;
import static org.junit.Assert.assertTrue;

import java.lang.reflect.Member;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;
import org.junit.Test;

public class DeoptTest {
    public static final class FakeBridge {
        static final List<Member> CALLS = new ArrayList<>();
        public static void deoptimizeMethod(Member m) { CALLS.add(m); }
    }

    public static final class ThrowingBridge {
        public static void deoptimizeMethod(Member m) { throw new IllegalStateException("boom"); }
    }

    public static final class InstanceBridge {
        public void deoptimizeMethod(Member m) {}
    }

    @Test
    public void missingFrameworkIsSkippedSilently() {
        assertNull(Deopt.resolve("de.robv.android.xposed.DoesNotExist"));
        assertFalse(Deopt.invoke(null, String.class.getDeclaredMethods()[0]));
        // Plain JVM has no XposedBridge: every entry point must be a no-op, never a crash.
        Deopt.constructors(StringBuilder.class);
        Deopt.constructor(StringBuilder.class, String.class);
        Deopt.method(String.class, "length");
        Deopt.method(String.class, "noSuchMethod");
        Deopt.member(null);
    }

    @Test
    public void legacyDeoptimizeMethodIsCalledWithTheHookedMember() throws Exception {
        Method deopt = Deopt.resolve(FakeBridge.class.getName());
        assertNotNull(deopt);
        Method target = String.class.getDeclaredMethod("length");
        FakeBridge.CALLS.clear();
        assertTrue(Deopt.invoke(deopt, target));
        assertEquals(1, FakeBridge.CALLS.size());
        assertEquals(target, FakeBridge.CALLS.get(0));
    }

    @Test
    public void failingDeoptimizeNeverPropagates() throws Exception {
        Method deopt = Deopt.resolve(ThrowingBridge.class.getName());
        assertNotNull(deopt);
        assertFalse(Deopt.invoke(deopt, String.class.getDeclaredMethod("length")));
    }

    @Test
    public void nonStaticDeoptimizeIsIgnored() {
        assertNull(Deopt.resolve(InstanceBridge.class.getName()));
    }
}
