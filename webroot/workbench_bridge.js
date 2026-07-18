// 洛书 v14.2 Alpha2 — 字体工作台独立字重桥接
// 通过 v14.2 字重兼容引擎生成真实轮廓，同时复用现有 v14 组合选择状态与重启保护。
import { exec } from './kernelsu.js';
import './workbench_weight_extension.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const MIX_BRIDGE = `${MODULE_DIR}/common/v14_mix.sh`;
const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';
const MIX_PENDING_KEY = 'luoshu_v14_pending_mix';
let applyingSelection = false;
let bypassApplyIntercept = false;

function clampWeight(value, fallback = 400) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.max(1, Math.min(1000, Math.round(number)));
}
function quote(value) { return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'"; }
function parseJson(output) {
    const line = String(output || '').split('\n').find(item => item.trim().startsWith('{'));
    if (!line) throw new Error('未收到有效组合任务状态');
    return JSON.parse(line.trim());
}
async function rawShell(command) {
    const result = await exec(command);
    const stdout = String(result?.stdout || '');
    const stderr = String(result?.stderr || '');
    if (Number(result?.errno || 0) !== 0) throw new Error(stderr.trim() || '命令执行失败');
    return stdout || stderr;
}
function normalizeSelection(selection = {}, fallback = {}) {
    return {
        enabled: Boolean(selection.enabled ?? fallback.enabled),
        cjk: String(selection.cjk || fallback.cjk || ''),
        latin: String(selection.latin || fallback.latin || ''),
        digit: String(selection.digit || fallback.digit || ''),
        cjkWeight: clampWeight(selection.cjkWeight ?? fallback.cjkWeight, 400),
        latinWeight: clampWeight(selection.latinWeight ?? fallback.latinWeight, 400),
        digitWeight: clampWeight(selection.digitWeight ?? fallback.digitWeight, 400),
    };
}
function readSelection() {
    try {
        const value = JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null') || {};
        return normalizeSelection(value);
    } catch (_) {
        return normalizeSelection({});
    }
}
function writeSelection(selection = {}) {
    const value = normalizeSelection(selection, readSelection());
    if (!value.cjk || !value.latin || !value.digit) return false;
    localStorage.setItem(MIX_LOCAL_KEY, JSON.stringify(value));
    updateVisibleMixNames(value);
    window.dispatchEvent(new CustomEvent('luoshu-mix-selection-change', { detail: value }));
    return true;
}
function fontName(id) {
    return window.App?.fonts?.find(item => item.id === id)?.name || id || '请选择';
}
function updateVisibleMixNames(value = readSelection()) {
    const ids = { cjk: 'mixCjkName', latin: 'mixLatinName', digit: 'mixDigitName' };
    const weights = { cjk: value.cjkWeight, latin: value.latinWeight, digit: value.digitWeight };
    Object.entries(ids).forEach(([slot, id]) => {
        const element = document.getElementById(id);
        if (element && value[slot]) element.textContent = `${fontName(value[slot])} · ${weights[slot]}`;
    });
}
async function waitFor(getter, timeoutMs = 7000, intervalMs = 50) {
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
function ensureProgress() {
    let box = document.getElementById('v14SwitchProgress');
    if (box) return box;
    box = document.createElement('div');
    box.id = 'v14SwitchProgress';
    box.className = 'v14-switch-progress';
    box.innerHTML = '<i></i><span><b>正在准备独立字重</b><small>请稍候，不需要离开页面</small></span>';
    document.body.appendChild(box);
    return box;
}
function setProgress(show, title = '正在准备独立字重', detail = '请稍候，不需要离开页面') {
    const box = ensureProgress();
    const titleElement = box.querySelector('b');
    const detailElement = box.querySelector('small');
    if (titleElement) titleElement.textContent = title;
    if (detailElement) detailElement.textContent = detail;
    box.classList.toggle('show', Boolean(show));
}
async function waitForMixTask(taskId, timeoutMs = 600000) {
    const started = Date.now();
    let interval = 850;
    while (Date.now() - started < timeoutMs) {
        await new Promise(resolve => setTimeout(resolve, interval));
        interval = Math.min(1800, interval + 120);
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} status ${quote(taskId)}`));
        if (result.status !== 'ok' || !result.data) continue;
        const progress = result.data.progress;
        if (progress?.message) setProgress(true, progress.message, `${Number(progress.percent || 0)}% · 中文 ${result.data.cjkWeight || 400} / 英文 ${result.data.latinWeight || 400} / 数字 ${result.data.digitWeight || 400}`);
        if (result.data.state === 'success' || result.data.state === 'failed') return result.data;
    }
    throw new Error('独立字重组合确认超时，后台任务可能仍在继续');
}
function finishWeightedMix(selection, status, recovered = false) {
    const app = window.App;
    localStorage.removeItem(MIX_PENDING_KEY);
    const finalSelection = normalizeSelection({ ...selection, ...status, enabled: true }, selection);
    writeSelection(finalSelection);
    app?.applyFontData?.({ current: 'mix', fonts: app.fonts, stats: app.stats });
    app?.saveLastSwitchResult?.({ status: 'success', font: '完整复合字体', time: Date.now(), message: status?.message || '' });
    if (app) {
        app.textRebootRequired = true;
        app.pendingFont = null;
        app.updateRebootUI?.();
        app.renderList?.();
    }
    updateVisibleMixNames(finalSelection);
    setProgress(false);
    app?.showToast?.(recovered ? '✓ 已确认独立字重字体组合' : '✓ 独立字重组合已准备，重启后生效');
    const summary = `中文 ${fontName(finalSelection.cjk)} ${finalSelection.cjkWeight} / 英文 ${fontName(finalSelection.latin)} ${finalSelection.latinWeight} / 数字 ${fontName(finalSelection.digit)} ${finalSelection.digitWeight}`;
    app?.showApplyDone?.('独立字重组合', summary);
}
async function applySelectionThroughUi(selection = readSelection()) {
    const app = window.App;
    const value = normalizeSelection(selection, readSelection());
    if (applyingSelection || app?.isSwitching) throw new Error('字体组合正在准备中');
    if (!value.cjk || !value.latin || !value.digit) throw new Error('请先选择中文、英文和数字字体');
    if (app?.textRebootRequired) throw new Error('本次开机已更改文字字体，请先重启手机');
    applyingSelection = true;
    if (app) app.isSwitching = true;
    document.body.classList.add('switching');
    setProgress(true, '正在同步组合选择', `中文 ${value.cjkWeight} / 英文 ${value.latinWeight} / 数字 ${value.digitWeight}`);
    try {
        await waitFor(() => window.App?.fonts?.length && document.getElementById('fontMixPanel'));
        await chooseSlot('cjk', value.cjk);
        await chooseSlot('latin', value.latin);
        await chooseSlot('digit', value.digit);
        writeSelection(value);
        setProgress(true, '正在实例化三个字体字重', '可变字体会固定到滑块数值，静态家族会选择最接近的真实档位');
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} start ${quote(value.cjk)} ${quote(value.latin)} ${quote(value.digit)} ${value.cjkWeight} ${value.latinWeight} ${value.digitWeight}`));
        if (result.status !== 'ok') throw new Error(result.message || '无法启动独立字重组合任务');
        const taskId = result.data?.task;
        if (!taskId) throw new Error('组合任务 ID 缺失');
        localStorage.setItem(MIX_PENDING_KEY, JSON.stringify({ task: taskId, started: Date.now(), ...value }));
        const status = await waitForMixTask(taskId);
        if (status.state !== 'success') throw new Error(status.message || '独立字重组合失败');
        finishWeightedMix(value, status, false);
        return true;
    } catch (error) {
        const message = String(error?.message || error);
        setProgress(false);
        if (/超时|后台任务/.test(message) && localStorage.getItem(MIX_PENDING_KEY)) app?.showToast?.('组合仍在后台处理，重新进入 WebUI 会自动确认');
        else {
            localStorage.removeItem(MIX_PENDING_KEY);
            app?.saveLastSwitchResult?.({ status: 'failed', font: '独立字重组合', time: Date.now(), message });
            app?.showToast?.(`组合失败：${message}`);
        }
        throw error;
    } finally {
        applyingSelection = false;
        if (app) app.isSwitching = false;
        document.body.classList.remove('switching');
    }
}
async function syncServerConfig() {
    try {
        await waitFor(() => window.App?.fonts?.length, 9000, 100);
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} config`));
        if (result.status === 'ok' && result.data?.cjk && result.data?.latin && result.data?.digit) writeSelection(result.data);
    } catch (_) { /* 配置同步失败不影响本地工作台 */ }
}

window.LuoShuV14 = window.LuoShuV14 || Object.freeze({
    getMixState: readSelection,
    setMixSelection: writeSelection,
    applyMix: applySelectionThroughUi,
    refreshMixPanel() { updateVisibleMixNames(); return true; },
});

// 首页原有“应用字体组合”改走独立字重桥，未设置时默认三个槽均为 400。
document.addEventListener('click', event => {
    const button = event.target?.closest?.('#applyFontMixBtn');
    if (!button || bypassApplyIntercept || applyingSelection) return;
    const selection = readSelection();
    if (!selection.cjk || !selection.latin || !selection.digit) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    bypassApplyIntercept = true;
    applySelectionThroughUi(selection).catch(() => {}).finally(() => {
        setTimeout(() => { bypassApplyIntercept = false; }, 500);
    });
}, true);

function markAlphaVersion() {
    document.querySelectorAll('[data-module-version]').forEach(element => { element.textContent = 'v14.2 Alpha2'; });
    const engine = document.getElementById('engineVersion');
    if (engine) engine.textContent = 'v14.2 Alpha2';
}
function initialize() {
    markAlphaVersion();
    updateVisibleMixNames();
    setTimeout(syncServerConfig, 360);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
