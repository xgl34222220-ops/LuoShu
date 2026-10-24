package io.github.xgl34222220.luoshu.globalfont;

import de.robv.android.xposed.XposedBridge;

final class Log {
    private Log() {}

    static volatile boolean verbose;

    static void v(String msg) {
        if (verbose) XposedBridge.log(ModuleConfig.TAG + ": " + msg);
    }
}
