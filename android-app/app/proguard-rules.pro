# Compose/library consumer rules are provided by dependencies.
# LSPosed loads the entry class by the literal name stored in assets/xposed_init.
-keep class io.github.xgl34222220.luoshu.xposed.LuoShuFontHook { *; }
-dontwarn de.robv.android.xposed.**
