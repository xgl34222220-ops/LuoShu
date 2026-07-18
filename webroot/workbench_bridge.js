// 洛书 v14.2 Alpha6 — 工作台/概览统一多轴组合桥
// 不再模拟点击旧选择器；直接启动异步多轴引擎并轮询包装任务。
import { exec } from './kernelsu.js';
import './workbench_weight_extension.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const MIX_BRIDGE = `${MODULE_DIR}/common/v14_mix.sh`;
const MIX_PENDING_KEY = 'luoshu_v14_pending_mix';
let applying = false;
let bypassApplyIntercept = false;

function quote(value) { return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'"; }
function parseJson(output) {
    const line = String(output || '').split('\n').find(item => item.trim().startsWith('{'));
    if (!line) throw new Error('未收到有效多轴任务状态');
    return JSON.parse(line.trim());
}
async function rawShell(command) {
    const result = await exec(command);
    const stdout = String(result?.stdout || '');
    const stderr = String(result?.stderr || '');
    if (Number(result?.errno || 0) !== 0) throw new Error(stderr.trim() || '命令执行失败');
    return stdout || stderr;
}
function axisUi() { return window.LuoShuAxisUI; }
function readSelection() { return axisUi()?.readState?.() || { cjk: '', latin: '', digit: '', cjkAxes: { wght: 400 }, latinAxes: { wght: 400 }, digitAxes: { wght: 400 } }; }
function normalizeSelection(selection = {}) {
    const current = readSelection();
    const next = { ...current, ...selection };
    ['cjk', 'latin', 'digit'].forEach(slot => {
        const key = `${slot}Axes`;
        next[key] = axisUi()?.parseAxisSpec?.(selection[key] ?? current[key]) || current[key] || { wght: 400 };
    });
    return next;
}
function writeSelection(selection = {}) {
    const value = normalizeSelection(selection);
    if (!value.cjk || !value.latin || !value.digit) return false;
    axisUi()?.writeState?.(value);
    updateVisibleNames(value);
    window.dispatchEvent(new CustomEvent('luoshu-mix-selection-change', { detail: value }));
    return true;
}
function fontName(id) { return window.App?.fonts?.find(item => item.id === id)?.name || id || '请选择'; }
function axesSummary(axes) {
    const entries = Object.entries(axes || {});
    if (!entries.length) return '默认';
    return entries.slice(0, 3).map(([tag, value]) => `${tag} ${Number.isInteger(Number(value)) ? Number(value) : Number(value).toFixed(1)}`).join(' · ') + (entries.length > 3 ? ` +${entries.length - 3}` : '');
}
function updateVisibleNames(value = readSelection()) {
    const ids = { cjk: 'mixCjkName', latin: 'mixLatinName', digit: 'mixDigitName' };
    Object.entries(ids).forEach(([slot, id]) => {
        const element = document.getElementById(id);
        if (element && value[slot]) element.textContent = `${fontName(value[slot])} · ${axesSummary(value[`${slot}Axes`])}`;
    });
}
function ensureProgress() {
    let box = document.getElementById('v14SwitchProgress');
    if (box) return box;
    box = document.createElement('div'); box.id = 'v14SwitchProgress'; box.className = 'v14-switch-progress';
    box.innerHTML = '<i></i><span><b>正在准备多轴组合</b><small>任务在后台运行，界面可以正常响应</small></span>';
    document.body.appendChild(box); return box;
}
function setProgress(show, title = '正在准备多轴组合', detail = '任务在后台运行，界面可以正常响应') {
    const box = ensureProgress();
    box.querySelector('b').textContent = title; box.querySelector('small').textContent = detail;
    box.classList.toggle('show', Boolean(show));
}
async function waitForTask(taskId, timeoutMs = 720000) {
    const started = Date.now(); let interval = 700;
    while (Date.now() - started < timeoutMs) {
        await new Promise(resolve => setTimeout(resolve, interval));
        interval = Math.min(1800, interval + 100);
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} status ${quote(taskId)}`));
        if (result.status !== 'ok' || !result.data) continue;
        const progress = result.data.progress || {};
        setProgress(true, progress.message || result.data.message || '多轴组合正在后台处理', `${Number(progress.percent || 0)}% · 可安全停留或切换页面`);
        if (result.data.state === 'success' || result.data.state === 'failed') return result.data;
    }
    throw new Error('多轴组合确认超时，后台任务可能仍在继续');
}
function selectionFromStatus(selection, status) {
    const next = normalizeSelection({ ...selection, ...status, enabled: true });
    ['cjk', 'latin', 'digit'].forEach(slot => {
        const raw = status?.[`${slot}Axes`];
        if (raw) next[`${slot}Axes`] = axisUi()?.parseAxisSpec?.(raw) || next[`${slot}Axes`];
    });
    return next;
}
function finish(selection, status, recovered = false) {
    const app = window.App;
    localStorage.removeItem(MIX_PENDING_KEY);
    const finalSelection = selectionFromStatus(selection, status);
    writeSelection(finalSelection);
    app?.applyFontData?.({ current: 'mix', fonts: app.fonts, stats: app.stats });
    app?.saveLastSwitchResult?.({ status: 'success', font: '完整多轴复合字体', time: Date.now(), message: status?.message || '' });
    if (app) {
        app.textRebootRequired = true; app.pendingFont = null; app.updateRebootUI?.(); app.renderList?.();
    }
    setProgress(false);
    app?.showToast?.(recovered ? '✓ 已确认多轴字体组合' : '✓ 多轴组合已准备，重启后生效');
    const summary = ['cjk', 'latin', 'digit'].map(slot => `${fontName(finalSelection[slot])}（${axesSummary(finalSelection[`${slot}Axes`])}）`).join(' / ');
    app?.showApplyDone?.('多轴字体组合', summary);
    axisUi()?.scheduleRender?.();
}
async function applyMix(selection = readSelection()) {
    const app = window.App;
    const value = normalizeSelection(selection);
    if (applying || app?.isSwitching) throw new Error('字体任务正在进行中');
    if (!value.cjk || !value.latin || !value.digit) throw new Error('请先选择中文、英文和数字字体');
    if (app?.textRebootRequired) throw new Error('本次开机已更改文字字体，请先重启手机');
    applying = true; if (app) app.isSwitching = true;
    document.body.classList.add('switching');
    writeSelection(value);
    const specs = ['cjk', 'latin', 'digit'].map(slot => axisUi()?.serializeAxes?.(value[`${slot}Axes`]) || 'wght=400');
    setProgress(true, '正在提交多轴组合任务', '后台任务会立即接管，不会再阻塞 WebUI');
    try {
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const command = `sh ${quote(MIX_BRIDGE)} start ${quote(value.cjk)} ${quote(value.latin)} ${quote(value.digit)} ${quote(specs[0])} ${quote(specs[1])} ${quote(specs[2])}`;
        const result = parseJson(await rawShell(command));
        if (result.status !== 'ok') throw new Error(result.message || '无法启动多轴组合任务');
        const taskId = result.data?.task;
        if (!taskId) throw new Error('多轴组合任务 ID 缺失');
        localStorage.setItem(MIX_PENDING_KEY, JSON.stringify({ task: taskId, started: Date.now(), ...value }));
        const status = await waitForTask(taskId);
        if (status.state !== 'success') throw new Error(status.message || '多轴组合失败');
        finish(value, status, false);
        return true;
    } catch (error) {
        const message = String(error?.message || error); setProgress(false);
        if (/超时|后台任务/.test(message) && localStorage.getItem(MIX_PENDING_KEY)) app?.showToast?.('任务仍在后台处理，重新进入 WebUI 会自动确认');
        else {
            localStorage.removeItem(MIX_PENDING_KEY);
            app?.saveLastSwitchResult?.({ status: 'failed', font: '多轴字体组合', time: Date.now(), message });
            app?.showToast?.(`组合失败：${message}`);
        }
        throw error;
    } finally {
        applying = false; if (app) app.isSwitching = false;
        document.body.classList.remove('switching'); axisUi()?.scheduleRender?.();
    }
}
async function recoverPending() {
    let pending;
    try { pending = JSON.parse(localStorage.getItem(MIX_PENDING_KEY) || 'null'); }
    catch (_) { localStorage.removeItem(MIX_PENDING_KEY); return; }
    if (!pending?.task || Date.now() - Number(pending.started || 0) > 900000) return;
    setProgress(true, '正在确认上次多轴组合', '后台任务可能已经完成');
    try {
        const status = await waitForTask(pending.task, 300000);
        if (status.state === 'success') finish(pending, status, true);
        else throw new Error(status.message || '多轴组合失败');
    } catch (error) {
        setProgress(false);
        if (!/超时|暂无|不存在/.test(String(error?.message || error))) {
            localStorage.removeItem(MIX_PENDING_KEY); window.App?.showToast?.(`组合失败：${error?.message || error}`);
        }
    }
}
async function syncServerConfig() {
    try {
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} config`));
        if (result.status !== 'ok' || !result.data?.cjk) return;
        const patch = { ...result.data };
        ['cjk', 'latin', 'digit'].forEach(slot => { if (patch[`${slot}Axes`]) patch[`${slot}Axes`] = axisUi()?.parseAxisSpec?.(patch[`${slot}Axes`]); });
        writeSelection(patch);
    } catch (_) { /* 不影响本地选择 */ }
}

window.LuoShuV14 = Object.freeze({ getMixState: readSelection, setMixSelection: writeSelection, applyMix, refreshMixPanel() { updateVisibleNames(); axisUi()?.scheduleRender?.(); return true; } });

document.addEventListener('click', event => {
    const button = event.target?.closest?.('#applyFontMixBtn');
    if (!button || bypassApplyIntercept || applying) return;
    event.preventDefault(); event.stopImmediatePropagation(); bypassApplyIntercept = true;
    applyMix(readSelection()).catch(() => {}).finally(() => setTimeout(() => { bypassApplyIntercept = false; }, 300));
}, true);

function markVersion() {
    document.querySelectorAll('[data-module-version]').forEach(element => { element.textContent = 'v14.2 Alpha6'; });
    const engine = document.getElementById('engineVersion'); if (engine) engine.textContent = 'v14.2 Alpha6';
}
function initialize() {
    markVersion(); updateVisibleNames();
    setTimeout(syncServerConfig, 300); setTimeout(recoverPending, 520);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
