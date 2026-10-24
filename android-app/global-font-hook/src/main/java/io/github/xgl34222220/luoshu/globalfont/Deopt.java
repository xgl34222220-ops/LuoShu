package io.github.xgl34222220.luoshu.globalfont;

import java.lang.reflect.Constructor;
import java.lang.reflect.Member;
import java.lang.reflect.Method;
import java.lang.reflect.Modifier;

/**
 * Asks the framework to deoptimize a method before it is hooked, so ART cannot keep an inlined or
 * AOT-compiled copy of it inside a caller and silently bypass the hook (same idea as MFGA-Xposed's
 * {@code deoptimize(method)} before each hook). Uses LSPosed's legacy
 * {@code XposedBridge.deoptimizeMethod(Member)} looked up by reflection: on a framework that lacks
 * it, or if the call fails, it is skipped silently and the hook is installed as before.
 */
final class Deopt {
    private Deopt() {}

    static final String BRIDGE = "de.robv.android.xposed.XposedBridge";
    private static final Method DEOPTIMIZE = resolve(BRIDGE);

    /** Returns the static {@code deoptimizeMethod(Member)} of {@code className}, or null. */
    static Method resolve(String className) {
        try {
            Method m = Class.forName(className, false, Deopt.class.getClassLoader())
                    .getDeclaredMethod("deoptimizeMethod", Member.class);
            if (!Modifier.isStatic(m.getModifiers())) return null;
            m.setAccessible(true);
            return m;
        } catch (Throwable t) {
            return null;
        }
    }

    static boolean available() {
        return DEOPTIMIZE != null;
    }

    /** Deoptimizes one method or constructor; never throws. */
    static boolean member(Member member) {
        return invoke(DEOPTIMIZE, member);
    }

    static boolean invoke(Method deoptimize, Member member) {
        if (deoptimize == null || member == null) return false;
        try {
            deoptimize.invoke(null, member);
            return true;
        } catch (Throwable t) {
            Log.v("deoptimize skipped: " + member + ": " + t);
            return false;
        }
    }

    /** Every declared constructor, matching {@code XposedBridge.hookAllConstructors}. */
    static void constructors(Class<?> type) {
        try {
            for (Constructor<?> c : type.getDeclaredConstructors()) member(c);
        } catch (Throwable ignored) {
            // A class that cannot list its constructors is hooked exactly as before.
        }
    }

    static void constructor(Class<?> type, Class<?>... params) {
        try {
            member(type.getDeclaredConstructor(params));
        } catch (Throwable ignored) {
        }
    }

    static void method(Class<?> type, String name, Class<?>... params) {
        try {
            member(type.getDeclaredMethod(name, params));
        } catch (Throwable ignored) {
        }
    }
}
