// 洛书 v14.2 Alpha1 — 字体工作台兼容桥接
// 通过现有 v14 组合面板完成应用，不进入底层生成与挂载实现。

const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';
const APPLY_AFTER_RELOAD_KEY = 'luoshu_v142_apply_after_reload';
let bypassApplyIntercept = false;

function readSelection() {
    try {
        const value = JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null') || {};
        return { enabled: false, cjk: String(value.cjk || ''), latin: String(value.latin || ''), digit: String(value.digit || '') };
    } catch (_) {
        return { enabled: false, cjk: '', latin: '', digit: '' };
    }
}

function writeSelection(selection = {}) {
    const value = {
        cjk: String(selection.cjk || ''),
        latin: String(selection.latin || ''),
        digit: String(selection.digit || ''),
    };
    if (!value.cjk || !value.latin || !value.digit) return false;
    localStorage.setItem(MIX_LOCAL_KEY, JSON.stringify(value));
    updateVisibleMixNames(value);
    return true;
}

function fontName(id) {
    return window.App?.fonts?.find(item => item.id === id)?.name || id || '请选择';
}

function updateVisibleMixNames(value = readSelection()) {
    const ids = { cjk: 'mixCjkName', latin: 'mixLatinName', digit: 'mixDigitName' };
    Object.entries(ids).forEach(([slot, id]) => {
        const el = document.getElementById(id);
        if (el && value[slot]) el.textContent = fontName(value[slot]);
    });
}

function reloadAndApply() {
    localStorage.setItem(APPLY_AFTER_RELOAD_KEY, '1');
    location.reload();
    return Promise.resolve();
}

window.LuoShuV14 = window.LuoShuV14 || Object.freeze({
    getMixState: readSelection,
    setMixSelection: writeSelection,
    applyMix: reloadAndApply,
    refreshMixPanel() { updateVisibleMixNames(); return true; },
});

// 首页“应用字体组合”也先读取工作台保存的预设，避免运行态仍持有旧选择。
document.addEventListener('click', event => {
    const button = event.target?.closest?.('#applyFontMixBtn');
    if (!button || bypassApplyIntercept) return;
    const selection = readSelection();
    if (!selection.cjk || !selection.latin || !selection.digit) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    reloadAndApply();
}, true);

async function applyPendingSelection() {
    if (localStorage.getItem(APPLY_AFTER_RELOAD_KEY) !== '1') return;
    for (let i = 0; i < 160; i += 1) {
        const button = document.getElementById('applyFontMixBtn');
        if (button && !button.disabled) {
            localStorage.removeItem(APPLY_AFTER_RELOAD_KEY);
            updateVisibleMixNames();
            bypassApplyIntercept = true;
            try { button.click(); }
            finally { setTimeout(() => { bypassApplyIntercept = false; }, 1000); }
            return;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    localStorage.removeItem(APPLY_AFTER_RELOAD_KEY);
    window.App?.showToast?.('组合面板尚未就绪，请返回首页后重试');
}

function markAlphaVersion() {
    document.querySelectorAll('[data-module-version]').forEach(el => { el.textContent = 'v14.2 Alpha1'; });
    const engine = document.getElementById('engineVersion');
    if (engine) engine.textContent = 'v14.2 Alpha1';
}

function initialize() {
    markAlphaVersion();
    updateVisibleMixNames();
    setTimeout(applyPendingSelection, 320);
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
