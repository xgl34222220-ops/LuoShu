# LuoShu uses no reflection-based serialization framework. Keep rules are
# intentionally minimal; Android/Compose consumer rules are supplied by their
# dependencies.

# Vector/LSPosed instantiates these classes by their fully-qualified names from assets/xposed_init.
-keep class io.github.xgl34222220.luoshu.hook.AppBundledFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.AppBundledFontHook
-keep class io.github.xgl34222220.luoshu.hook.ClockIconTypefaceSafetyHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.ClockIconTypefaceSafetyHook
-keep class io.github.xgl34222220.luoshu.hook.QqFontCompatibilityHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.QqFontCompatibilityHook
-keep class io.github.xgl34222220.luoshu.hook.ColorOsPlayFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.ColorOsPlayFontHook
-keep class io.github.xgl34222220.luoshu.hook.ColorOsPlayDownloadedFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.ColorOsPlayDownloadedFontHook
