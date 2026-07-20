# LuoShu uses no reflection-based serialization framework. Keep rules are
# intentionally minimal; Android/Compose consumer rules are supplied by their
# dependencies.

# Vector/LSPosed instantiates these classes by their fully-qualified names from assets/xposed_init.
-keep class io.github.xgl34222220.luoshu.hook.AppBundledFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.AppBundledFontHook
-keep class io.github.xgl34222220.luoshu.hook.ColorOsPlayFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.ColorOsPlayFontHook
