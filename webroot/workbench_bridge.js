// 洛书 v14.2 Alpha1 — 字体工作台兼容桥接
// 通过现有 v14 组合选择器和应用按钮完成操作，不进入底层生成与挂载实现。

const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';
let applyingSelection = false;
let bypassApplyIntercept = false;

function readSelection() {
    try {
        const value = JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null') || {};
        return {
            enabled: false,
            cjk: String(value.cjk || ''),
            latin: String(value.latin || ''),
            digit: String(value.digit || ''),
        };
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

async function waitFor(getter, timeoutMs = 6000, intervalMs = 50) {
    const started = Date.now();
    while (Date.now() - started < timeoutMs) {
        const value = getter();
        if (value) return value;
        await new Promise(resolve => setTimeout(resolve, intervalMs));
    }
    throw new Error('字体组合界面尚未就绪');
}

async function chooseSlot(slot, fontId) {
    const slotButton = await waitFor(() => document.querySelector(`[data-mix-slot="${slot}"]`));
    slotButton.click();
    const modal = await waitFor(() => {
        const value = document.getElementById('fontMixPicker');
        return value?.classList.contains('show') ? value : null;
    });
    const item = await waitFor(() => [...modal.querySelectorAll('[data-mix-font]')].find(button => button.dataset.mixFont === fontId));
    item.click();
    await waitFor(() => !modal.classList.contains('show'));
}

async function applySelectionThroughUi(selection = readSelection()) {
    if (applyingSelection) throw new Error('字体组合正在准备中');
    if (!selection.cjk || !selection.latin || !selection.digit) throw new Error('请先选择中文、英文和数字字体');
    applyingSelection = true;
    try {
        await waitFor(() => window.App?.fonts?.length && document.getElementById('fontMixPanel'));
        await chooseSlot('cjk', selection.cjk);
        await chooseSlot('latin', selection.latin);
        await chooseSlot('digit', selection.digit);
        updateVisibleMixNames(selection);
        const applyButton = await waitFor(() => {
            const button = document.getElementById('applyFontMixBtn');
            return button && !button.disabled ? button : null;
        });
        bypassApplyIntercept = true;
        try { applyButton.click(); }
        finally { setTimeout(() => { bypassApplyIntercept = false; }, 500); }
        return true;
    } finally {
        applyingSelection = false;
    }
}

window.LuoShuV14 = window.LuoShuV14 || Object.freeze({
    getMixState: readSelection,
    setMixSelection: writeSelection,
    applyMix: applySelectionThroughUi,
    refreshMixPanel() { updateVisibleMixNames(); return true; },
});

// 首页原有“应用字体组合”也先把 localStorage 中的选择写入真实 v14 选择器，
// 避免已启用的旧服务端配置覆盖刚保存的工作台预设。
document.addEventListener('click', event => {
    const button = event.target?.closest?.('#applyFontMixBtn');
    if (!button || bypassApplyIntercept || applyingSelection) return;
    const selection = readSelection();
    if (!selection.cjk || !selection.latin || !selection.digit) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    applySelectionThroughUi(selection).catch(error => {
        window.App?.showToast?.(`组合预设同步失败：${error?.message || String(error)}`);
    });
}, true);

function markAlphaVersion() {
    document.querySelectorAll('[data-module-version]').forEach(el => { el.textContent = 'v14.2 Alpha1'; });
    const engine = document.getElementById('engineVersion');
    if (engine) engine.textContent = 'v14.2 Alpha1';
}

function initialize() {
    markAlphaVersion();
    updateVisibleMixNames();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
