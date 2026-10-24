# LSPosed loads io.github.xgl34222220.luoshu.globalfont.HookEntry by name (assets/xposed_init) and the
# App calls ModuleStatus.isModuleActive(), which the module replaces in the App's own process. Keep the
# whole module package unshrunk and unrenamed so both names resolve and isModuleActive is never inlined.
-keep class io.github.xgl34222220.luoshu.globalfont.** { *; }
# XposedBridge API is compileOnly: LSPosed provides it inside hooked processes.
-dontwarn de.robv.android.xposed.**
