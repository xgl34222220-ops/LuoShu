package io.github.xgl34222220.luoshu.fontcontract;

/** Exact read-only targets of the disposable module-payload experiment. */
final class DirectFontPaths {
    static boolean allowed(String path) {
        if (path == null || path.contains("..")) return false;
        if (path.startsWith("/system/fonts/LuoShu") && path.indexOf('/', "/system/fonts/".length()) < 0) return true;
        switch (path) {
            case "/system/fonts/NotoColorEmoji.ttf":
            case "/system/fonts/AndroidClock.ttf":
            case "/system/fonts/DroidSans.ttf":
            case "/system/fonts/DroidSans-Bold.ttf":
            case "/system/fonts/RobotoStatic-Regular.ttf":
                return true;
            default:
                return false;
        }
    }
    private DirectFontPaths() {}
}
