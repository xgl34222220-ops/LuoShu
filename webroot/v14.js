// 洛书 v14：稳定切换、自动权限兼容与精简自救界面。
import { exec } from './kernelsu.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const FONT_MANAGER = `${MODULE_DIR}/common/font_manager.sh`;
const SWITCH_BRIDGE = `${MODULE_DIR}/common/v14_switch.sh`;
const PENDING_KEY = 'luoshu_v14_pending_switch';

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function quote(value) { return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'"; }
function parseJson(output) {
    const line = String(output || '').split('\n').find(item => item.trim().startsWith('{'));
    if (!line) throw new Error('未收到有效任务状态');
    return JSON.parse(line.trim());
}

async function rawShell(command) {
    const result = await exec(command);
    const stdout = String(result?.stdout || '');
    const stderr = String(result?.stderr || '');
    if (Number(result?.errno || 0) !== 0) throw new Error(stderr.trim() || '命令执行失败');
    return stdout || stderr;
}

function normalizeManagerCommand(command) {
    const text = String(command || '');
    if (text === FONT_MANAGER) return `sh ${quote(FONT_MANAGER)}`;
    if (text.startsWith(`${FONT_MANAGER} `)) return `sh ${quote(FONT_MANAGER)}${text.slice(FONT_MANAGER.length)}`;
    return text;
}

function ensureProgress() {
    let box = document.getElementById('v14SwitchProgress');
    if (box) return box;
    box = document.createElement('div');
    box.id = 'v14SwitchProgress';
    box.className = 'v14-switch-progress';
    box.innerHTML = '<i></i><span><b>正在准备字体</b><small>请稍候，不需要离开页面</small></span>';
    document.body.appendChild(box);
    return box;
}

function setProgress(show, title = '正在准备字体', detail = '请稍候，不需要离开页面') {
    const box = ensureProgress();
    box.querySelector('b').textContent = title;
    box.querySelector('small').textContent = detail;
    box.classList.toggle('show', Boolean(show));
}

function updateEngineCopy(app) {
    const paragraph = document.querySelector('.engine-copy p');
    if (!paragraph) return;
    const font = app.fonts?.find(item => item.id === app.currentFont);
    const name = !app.currentFont || app.currentFont === 'default' ? '系统默认字体' : (font?.name || app.currentFont);
    paragraph.textContent = `当前字体：${name}`;
}

function finishSwitch(app, fontId, status, recovered = false) {
    localStorage.removeItem(PENDING_KEY);
    app.applyFontData({ current: fontId, fonts: app.fonts, stats: app.stats });
    app.recordUsage(fontId);
    const displayName = fontId === 'default' ? '系统默认字体' : (app.fonts.find(item => item.id === fontId)?.name || fontId);
    app.saveLastSwitchResult({ status: 'success', font: displayName, time: Date.now(), message: status?.message || '' });
    app.textRebootRequired = true;
    app.pendingFont = null;
    app.updateRebootUI();
    app.renderList();
    updateEngineCopy(app);
    setProgress(false);
    app.showToast(recovered ? `✓ 已确认切换到 ${displayName}` : '✓ 字体已准备，重启后全局生效');
    app.showApplyDone('文字字体', displayName);
}

async function recoverPending(app) {
    let pending;
    try { pending = JSON.parse(localStorage.getItem(PENDING_KEY) || 'null'); }
    catch (_) { localStorage.removeItem(PENDING_KEY); return; }
    if (!pending?.task || !pending?.fontId) return;
    if (Date.now() - Number(pending.started || 0) > 180000) {
        localStorage.removeItem(PENDING_KEY);
        return;
    }
    setProgress(true, '正在确认上次切换', '字体任务已在后台继续执行');
    try {
        const status = await app.waitForSwitchTask(pending.task, 45000);
        if (status.state === 'success') finishSwitch(app, pending.fontId, status, true);
        else throw new Error(status.message || '字体应用失败');
    } catch (error) {
        setProgress(false);
        if (/超时|暂无|不存在/.test(String(error?.message || error))) {
            app.showToast('后台任务尚未确认，可稍后重新进入查看');
        } else {
            localStorage.removeItem(PENDING_KEY);
            app.saveLastSwitchResult({ status: 'failed', font: pending.fontId, time: Date.now(), message: String(error?.message || error) });
            app.showToast('切换失败: ' + String(error?.message || error));
        }
    }
}

function simplifyStabilityUi() {
    document.querySelectorAll('[data-stability-action="permissions"],[data-stability-action="rollback"]').forEach(node => node.remove());
    document.querySelectorAll('.stability-note').forEach(node => node.remove());
    document.querySelectorAll('.stability-health').forEach(node => {
        const title = node.querySelector('b')?.textContent || '';
        if (title.includes('脚本权限')) node.remove();
    });
    document.querySelectorAll('.stability-info-grid > div').forEach(node => {
        const title = node.querySelector('small')?.textContent || '';
        if (title.includes('上一个稳定配置')) node.remove();
    });
    const row = document.getElementById('openStabilityBtn');
    if (row) {
        const title = row.querySelector('strong');
        const detail = row.querySelector('small');
        if (title) title.textContent = 'WebUI 修复工具';
        if (detail) detail.textContent = '清理缓存、重建字体索引与生成报告';
    }
}

function installUiObserver() {
    let queued = false;
    const run = () => {
        queued = false;
        simplifyStabilityUi();
    };
    const observer = new MutationObserver(() => {
        if (queued) return;
        queued = true;
        requestAnimationFrame(run);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    simplifyStabilityUi();
}

function patchApp() {
    const app = window.App;
    if (!app || app.__v14Patched) return false;
    app.__v14Patched = true;

    const originalExecShell = app.execShell.bind(app);
    app.execShell = function(command) {
        return originalExecShell(normalizeManagerCommand(command));
    };

    const originalRenderCurrent = app.renderCurrent.bind(app);
    app.renderCurrent = function() {
        originalRenderCurrent();
        updateEngineCopy(this);
    };

    app.waitForSwitchTask = async function(taskId, timeoutMs = 60000) {
        const started = Date.now();
        let interval = 850;
        while (Date.now() - started < timeoutMs) {
            await sleep(interval);
            interval = Math.min(1600, interval + 120);
            const output = await rawShell(`sh ${quote(SWITCH_BRIDGE)} status ${quote(taskId)}`);
            const result = parseJson(output);
            if (result.status !== 'ok' || !result.data) continue;
            if (result.data.state === 'success' || result.data.state === 'failed') return result.data;
        }
        throw new Error('切换确认超时，后台任务可能仍在继续');
    };

    app.switchFont = async function(fontId) {
        if (this.isSwitching) { this.showToast('字体切换正在进行中'); return; }
        this.isSwitching = true;
        this.pendingFont = null;
        document.body.classList.add('switching');
        setProgress(true, fontId === 'default' ? '正在恢复系统字体' : '正在准备新字体', '后台安全写入中，请不要重复点击');
        try {
            await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
            const output = await rawShell(`sh ${quote(SWITCH_BRIDGE)} start ${quote(fontId)}`);
            const result = parseJson(output);
            if (result.status !== 'ok') throw new Error(result.message || '无法启动切换任务');
            const taskId = result.data?.task;
            if (!taskId) throw new Error('切换任务 ID 缺失');
            localStorage.setItem(PENDING_KEY, JSON.stringify({ task: taskId, fontId, started: Date.now() }));
            const status = await this.waitForSwitchTask(taskId);
            if (status.state !== 'success') throw new Error(status.message || '字体应用失败');
            finishSwitch(this, fontId, status, false);
        } catch (error) {
            const message = String(error?.message || error);
            setProgress(false);
            if (/超时|后台任务/.test(message) && localStorage.getItem(PENDING_KEY)) {
                this.showToast('字体仍在后台处理，重新进入 WebUI 会自动确认');
            } else {
                localStorage.removeItem(PENDING_KEY);
                this.saveLastSwitchResult({ status: 'failed', font: fontId === 'default' ? '系统默认字体' : fontId, time: Date.now(), message });
                this.showToast('切换失败: ' + message);
            }
        } finally {
            this.isSwitching = false;
            document.body.classList.remove('switching');
        }
    };

    const originalInit = app.init.bind(app);
    app.init = async function() {
        await originalInit();
        updateEngineCopy(this);
        setTimeout(() => recoverPending(this), 180);
    };

    document.documentElement.classList.add('luoshu-v14');
    return true;
}

if (!patchApp()) {
    const timer = setInterval(() => { if (patchApp()) clearInterval(timer); }, 20);
    setTimeout(() => clearInterval(timer), 3000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installUiObserver, { once: true });
} else installUiObserver();
