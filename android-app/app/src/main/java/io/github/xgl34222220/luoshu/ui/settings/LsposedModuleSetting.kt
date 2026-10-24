package io.github.xgl34222220.luoshu.ui.settings

/** 全局字体（LSPosed）：洛书 App 本身就是 LSPosed 模块；这里只读激活状态，不在洛书进程里安装任何 Hook。 */
internal data class LsposedModuleState(
    val activated: Boolean = false,
    val legacyCompanion: Boolean = false,
)

internal const val LSPOSED_MODULE_TITLE = "全局字体（LSPosed）"

internal const val LSPOSED_MODULE_DESCRIPTION =
    "洛书已内置 LSPosed 全局字体模块，无需再安装独立伴随 App。在 LSPosed 中启用洛书并勾选作用域" +
        "（需要生效的 App），重启这些 App 后，它们自带的正文字体与 WebView 网页字体会跟随系统字体。" +
        "Hook 只运行在作用域内的 App 里，洛书自身不受影响。"

internal fun lsposedModuleStatusText(state: LsposedModuleState): String = buildString {
    append(
        if (state.activated) "LSPosed 已激活本模块。作用域内的 App 重启后生效。"
        else "LSPosed 尚未激活本模块：请在 LSPosed 中启用洛书并勾选作用域。",
    )
    if (state.legacyCompanion) {
        append("\n检测到旧版独立伴随 App「洛书全局字体」，可在 LSPosed 中停用后卸载；两者同时启用时同一进程只替换一次。")
    }
}
