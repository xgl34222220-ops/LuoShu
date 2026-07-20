# LuoShu uses no reflection-based serialization framework. Keep rules are
# intentionally minimal; Android/Compose consumer rules are supplied by their
# dependencies.

# Vector/LSPosed instantiates this class by its fully-qualified name from assets/xposed_init.
-keep class io.github.xgl34222220.luoshu.hook.AppBundledFontHook { *; }
-keepnames class io.github.xgl34222220.luoshu.hook.AppBundledFontHook
