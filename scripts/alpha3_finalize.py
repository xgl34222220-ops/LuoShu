#!/usr/bin/env python3
from pathlib import Path


def rep(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing token in {path}: {old[:100]!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


rep(
    "webroot/workbench_weight_extension.js",
    """function writeState(next = {}) {
    const current = readState();
    const merged = normalizeState({ ...current, ...next });
    localStorage.setItem(MIX_LOCAL_KEY, JSON.stringify(merged));
    window.dispatchEvent(new CustomEvent('luoshu-axis-state-change', { detail: merged }));
    return merged;
}""",
    """function writeState(next = {}) {
    const current = readState();
    const merged = normalizeState({ ...current, ...next });
    const serialized = JSON.stringify(merged);
    if (localStorage.getItem(MIX_LOCAL_KEY) === serialized) return merged;
    localStorage.setItem(MIX_LOCAL_KEY, serialized);
    window.dispatchEvent(new CustomEvent('luoshu-axis-state-change', { detail: merged }));
    return merged;
}""",
)
rep(
    "webroot/workbench_weight_extension.js",
    """    requestAnimationFrame(async () => {
        renderScheduled = false;
        ensureOverviewPanel();""",
    """    requestAnimationFrame(async () => {
        renderScheduled = false;
        document.querySelectorAll('.workbench-version').forEach(element => { element.textContent = 'v14.2 Alpha3'; });
        ensureOverviewPanel();""",
)
rep(
    "webroot/workbench_weight_extension.js",
    """function initialize() {
    installStyles(); bindDelegatedEvents();
    const observer = new MutationObserver(scheduleRender);
    observer.observe(document.documentElement, { childList: true, subtree: true, characterData: true });
    ['luoshu-mix-selection-change', 'luoshu-font-slot-change', 'luoshu-axis-state-change'].forEach(name => window.addEventListener(name, scheduleRender));
    scheduleRender();
}""",
    """function initialize() {
    installStyles(); bindDelegatedEvents();
    const observer = new MutationObserver(mutations => {
        const relevant = mutations.some(mutation => {
            const target = mutation.target?.nodeType === 1 ? mutation.target : mutation.target?.parentElement;
            return !target?.closest?.('[data-axis-control], #mixAxisPanel');
        });
        if (relevant) scheduleRender();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    ['luoshu-mix-selection-change', 'luoshu-font-slot-change', 'luoshu-mix-storage-change'].forEach(name => window.addEventListener(name, scheduleRender));
    scheduleRender();
}""",
)
rep(
    "webroot/mix_state_guard.js",
    "    const merged = { ...current, ...incoming };\n    SLOTS.forEach(slot => {",
    "    const merged = { ...current, ...incoming };\n    let fontChangedAny = false;\n    SLOTS.forEach(slot => {",
)
rep(
    "webroot/mix_state_guard.js",
    "        if (fontChanged && !Object.prototype.hasOwnProperty.call(incoming, axesKey)) {\n            merged[axesKey] = {};",
    "        if (fontChanged && !Object.prototype.hasOwnProperty.call(incoming, axesKey)) {\n            fontChangedAny = true;\n            merged[axesKey] = {};",
)
rep(
    "webroot/mix_state_guard.js",
    "        queueMicrotask(() => window.dispatchEvent(new CustomEvent('luoshu-mix-storage-change', { detail: merged })));",
    "        if (fontChangedAny) queueMicrotask(() => window.dispatchEvent(new CustomEvent('luoshu-mix-storage-change', { detail: merged })));",
)
rep(
    "webroot/workbench_bridge.js",
    "    app?.applyFontData?.({ current: 'mix', fonts: app.fonts, stats: app.stats });\n    app?.saveLastSwitchResult?.",
    "    app?.applyFontData?.({ current: 'mix', fonts: app.fonts, stats: app.stats });\n    updateVisibleNames(finalSelection);\n    app?.saveLastSwitchResult?.",
)

for name in ("customize.sh", "post-fs-data.sh", "service.sh"):
    path = Path(name)
    path.write_text(
        path.read_text(encoding="utf-8")
        .replace("v14.2 Alpha2", "v14.2 Alpha3")
        .replace("Alpha2", "Alpha3"),
        encoding="utf-8",
    )

path = Path("common/font_manager.sh")
path.write_text(path.read_text(encoding="utf-8").replace("v14.1.1 RC3", "v14.2 Alpha3"), encoding="utf-8")

path = Path("webroot/workbench.js")
text = path.read_text(encoding="utf-8")
text = text.replace("v14.2 Alpha1", "v14.2 Alpha3").replace("workbench.css?v=14201", "workbench.css?v=14203")
text = text.replace(
    "Alpha1 先提供完整轴的实时预览与参数导出；真正写入复合字体将在后续版本接入生成引擎。",
    "这里可独立预览全部轴；要写入最终组合字体，请在“组合”页或概览组合区调节对应字体槽。",
)
path.write_text(text, encoding="utf-8")

path = Path("webroot/workbench.css")
path.write_text(path.read_text(encoding="utf-8").replace("v14.2 Alpha1", "v14.2 Alpha3"), encoding="utf-8")

path = Path(".github/workflows/check.yml")
text = path.read_text(encoding="utf-8").replace("v14.2 Alpha2", "v14.2 Alpha3").replace("14202", "14203")
text = text.replace(
    "      - RELEASE_NOTES_v14.2_ALPHA1.md\n",
    "      - RELEASE_NOTES_v14.2_ALPHA1.md\n      - RELEASE_NOTES_v14.2_ALPHA3.md\n",
)
text = text.replace(
    "          grep -qx 'webroot/workbench.js' /tmp/luoshu-package-list.txt\n",
    "          grep -qx 'webroot/workbench.js' /tmp/luoshu-package-list.txt\n          grep -qx 'webroot/mix_state_guard.js' /tmp/luoshu-package-list.txt\n",
)
text = text.replace(
    "          unzip -p \"$asset\" common/font_instance.py | grep -q 'instantiateVariableFont'\n",
    "          unzip -p \"$asset\" common/font_instance.py | grep -q 'instantiateVariableFont'\n          unzip -p \"$asset\" common/font_instance.py | grep -q -- '--axes'\n          unzip -p \"$asset\" common/v142_weighted_mix.sh | grep -q 'worker \"$_request\"'\n          unzip -p \"$asset\" webroot/workbench_weight_extension.css | grep -q 'mix-axis-panel'\n",
)
path.write_text(text, encoding="utf-8")

for cleanup in (
    ".github/workflows/alpha3-finalize.yml",
    ".github/workflows/alpha3-push-finalize.yml",
    "docs/.alpha3-sync-trigger",
    "docs/.alpha3-push-trigger",
    "scripts/alpha3_finalize.py",
):
    Path(cleanup).unlink(missing_ok=True)
