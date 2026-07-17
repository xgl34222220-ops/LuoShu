// 洛书 v14：稳定切换、精简设置与中文 / 英文 / 数字字体组合。
import { exec } from './kernelsu.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const FONT_MANAGER = `${MODULE_DIR}/common/font_manager.sh`;
const SWITCH_BRIDGE = `${MODULE_DIR}/common/v14_switch.sh`;
const MIX_BRIDGE = `${MODULE_DIR}/common/v14_mix.sh`;
const PENDING_KEY = 'luoshu_v14_pending_switch';
const MIX_PENDING_KEY = 'luoshu_v14_pending_mix';
const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';

const mixState = { enabled: false, cjk: '', latin: '', digit: '', selecting: '', initialized: false };

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }
function quote(value) { return "'" + String(value ?? '').replace(/'/g, "'\\''") + "'"; }
function parseJson(output) {
    const line = String(output || '').split('\n').find(item => item.trim().startsWith('{'));
    if (!line) throw new Error('未收到有效任务状态');
    return JSON.parse(line.trim());
}
function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
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

function fontName(app, id) {
    if (!id || id === 'default') return '系统默认';
    return app.fonts?.find(item => item.id === id)?.name || id;
}

function mixSummary(app, separator = ' · ') {
    return `中文 ${fontName(app, mixState.cjk)}${separator}英文 ${fontName(app, mixState.latin)}${separator}数字 ${fontName(app, mixState.digit)}`;
}

function updateEngineCopy(app) {
    const paragraph = document.querySelector('.engine-copy p');
    if (!paragraph) return;
    if (app.currentFont === 'mix') paragraph.textContent = '当前字体：完整复合字体';
    else paragraph.textContent = `当前字体：${fontName(app, app.currentFont)}`;
}

function renderMixedCurrent(app) {
    if (app.currentFont !== 'mix') return false;
    const nameEl = document.getElementById('currentFontName');
    const descEl = document.getElementById('currentFontDesc');
    const mainEl = document.getElementById('previewMain');
    const fullEl = document.getElementById('previewFull');
    const formatEl = document.getElementById('currentFormat');
    const sizeEl = document.getElementById('currentFontSize');
    const weightsEl = document.getElementById('currentWeights');
    if (nameEl) nameEl.textContent = '完整复合字体';
    if (descEl) descEl.textContent = mixSummary(app);
    if (mainEl) { mainEl.textContent = '中文 Aa 123'; mainEl.style.fontFamily = ''; }
    if (fullEl) { fullEl.textContent = '中文、English 与 123 来自同一份完整复合字体'; fullEl.style.fontFamily = ''; }
    if (formatEl) formatEl.textContent = 'COMPOSITE';
    if (sizeEl) sizeEl.textContent = '完整字体';
    if (weightsEl) weightsEl.innerHTML = '<span class="weight-tag regular">中文</span><span class="weight-tag medium">英文</span><span class="weight-tag bold">数字</span>';
    return true;
}

function saveMixLocal() {
    try { localStorage.setItem(MIX_LOCAL_KEY, JSON.stringify({ cjk: mixState.cjk, latin: mixState.latin, digit: mixState.digit })); }
    catch (_) { /* WebView 存储失败不影响使用 */ }
}
function loadMixLocal() {
    try {
        const saved = JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null');
        if (saved) {
            mixState.cjk = String(saved.cjk || '');
            mixState.latin = String(saved.latin || '');
            mixState.digit = String(saved.digit || '');
        }
    } catch (_) { /* ignore */ }
}

function validMixId(app, id) { return Boolean(id && app.fonts?.some(item => item.id === id && item.valid !== false)); }
function ensureMixDefaults(app) {
    const fallback = app.currentFont && app.currentFont !== 'default' && app.currentFont !== 'mix' && validMixId(app, app.currentFont)
        ? app.currentFont
        : (app.fonts?.find(item => item.id !== 'default' && item.valid !== false)?.id || '');
    if (!validMixId(app, mixState.cjk)) mixState.cjk = fallback;
    if (!validMixId(app, mixState.latin)) mixState.latin = mixState.cjk || fallback;
    if (!validMixId(app, mixState.digit)) mixState.digit = mixState.latin || mixState.cjk || fallback;
    saveMixLocal();
}

function injectMixPanel(app) {
    let panel = document.getElementById('fontMixPanel');
    if (!panel) {
        panel = document.createElement('section');
        panel.id = 'fontMixPanel';
        panel.className = 'font-mix-panel';
        panel.innerHTML = `
            <div class="mix-head">
                <div><span class="mix-kicker">字体组合</span><h2>中文为完整基底，英文与数字替换字形</h2><p>三款字体合成为同一份完整字体；所有系统槽使用相同文件，不依赖缺字回退。</p></div>
                <span class="mix-status" id="mixStatus">未启用</span>
            </div>
            <div class="mix-slots">
                <button class="mix-slot cjk" type="button" data-mix-slot="cjk"><span class="mix-slot-mark">中</span><span><small>中文字体</small><b id="mixCjkName">请选择</b><em>系统中文与 CJK 入口</em></span><i>›</i></button>
                <button class="mix-slot latin" type="button" data-mix-slot="latin"><span class="mix-slot-mark">Aa</span><span><small>英文字体</small><b id="mixLatinName">请选择</b><em>英文、Google Sans 与拉丁入口</em></span><i>›</i></button>
                <button class="mix-slot digit" type="button" data-mix-slot="digit"><span class="mix-slot-mark">123</span><span><small>数字字体</small><b id="mixDigitName">请选择</b><em>时钟、DIN 与 ROM 数字入口</em></span><i>›</i></button>
            </div>
            <div class="mix-foot"><p>中文覆盖始终来自中文基底；英文与数字只导入对应字形，不会携带源字体中的中文字形。</p><button id="applyFontMixBtn" type="button">应用字体组合</button></div>`;
        document.getElementById('listSection')?.insertAdjacentElement('beforebegin', panel);
        panel.querySelectorAll('[data-mix-slot]').forEach(button => button.addEventListener('click', () => openMixPicker(app, button.dataset.mixSlot)));
        panel.querySelector('#applyFontMixBtn')?.addEventListener('click', () => applyFontMix(app));
    }
    ensureMixPicker(app);
    renderMixPanel(app);
}

function renderMixPanel(app) {
    const panel = document.getElementById('fontMixPanel');
    if (!panel) return;
    ensureMixDefaults(app);
    const map = { cjk: 'mixCjkName', latin: 'mixLatinName', digit: 'mixDigitName' };
    Object.entries(map).forEach(([slot, id]) => { const el = document.getElementById(id); if (el) el.textContent = fontName(app, mixState[slot]) || '请选择'; });
    const status = document.getElementById('mixStatus');
    if (status) { status.textContent = app.currentFont === 'mix' || mixState.enabled ? '当前启用' : '可选功能'; status.classList.toggle('active', app.currentFont === 'mix' || mixState.enabled); }
    const button = document.getElementById('applyFontMixBtn');
    if (button) button.disabled = !mixState.cjk || !mixState.latin || !mixState.digit || app.isSwitching;
}

function ensureMixPicker(app) {
    let modal = document.getElementById('fontMixPicker');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'fontMixPicker';
    modal.className = 'mix-picker-modal';
    modal.innerHTML = `
        <div class="mix-picker-sheet" role="dialog" aria-modal="true">
            <div class="mix-picker-handle"></div>
            <div class="mix-picker-head"><div><small id="mixPickerKicker">选择字体</small><h3 id="mixPickerTitle">中文字体</h3></div><button id="mixPickerClose" type="button">×</button></div>
            <div class="mix-picker-search"><input id="mixPickerSearch" type="search" placeholder="搜索字体名称" autocomplete="off"></div>
            <div class="mix-picker-list" id="mixPickerList"></div>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', event => { if (event.target === modal) closeMixPicker(); });
    modal.querySelector('#mixPickerClose')?.addEventListener('click', closeMixPicker);
    modal.querySelector('#mixPickerSearch')?.addEventListener('input', () => renderMixPickerList(app));
    return modal;
}

function openMixPicker(app, slot) {
    mixState.selecting = slot;
    const labels = { cjk: ['中文槽', '选择中文字体'], latin: ['英文槽', '选择英文字体'], digit: ['数字槽', '选择数字字体'] };
    const [kicker, title] = labels[slot] || labels.cjk;
    const modal = ensureMixPicker(app);
    modal.querySelector('#mixPickerKicker').textContent = kicker;
    modal.querySelector('#mixPickerTitle').textContent = title;
    const input = modal.querySelector('#mixPickerSearch');
    if (input) input.value = '';
    renderMixPickerList(app);
    modal.classList.add('show');
    document.body.classList.add('mix-picker-open');
}
function closeMixPicker() {
    document.getElementById('fontMixPicker')?.classList.remove('show');
    document.body.classList.remove('mix-picker-open');
}
function renderMixPickerList(app) {
    const list = document.getElementById('mixPickerList');
    if (!list) return;
    const query = (document.getElementById('mixPickerSearch')?.value || '').trim().toLowerCase();
    const fonts = (app.fonts || []).filter(item => item.id !== 'default' && item.valid !== false && (!query || `${item.name || ''} ${item.id || ''}`.toLowerCase().includes(query)));
    if (!fonts.length) { list.innerHTML = '<div class="mix-picker-empty">没有找到可用字体</div>'; return; }
    list.innerHTML = fonts.map(item => {
        const active = item.id === mixState[mixState.selecting];
        const weights = Array.isArray(item.weights) ? item.weights.length : 1;
        return `<button class="mix-picker-item ${active ? 'active' : ''}" type="button" data-mix-font="${escapeHtml(item.id)}"><span class="mix-picker-preview">Aa</span><span><b>${escapeHtml(item.name || item.id)}</b><small>${escapeHtml(item.format || 'TTF')} · ${escapeHtml(item.size || '')} · ${weights} 档字重</small></span><i>${active ? '✓' : '›'}</i></button>`;
    }).join('');
    list.querySelectorAll('[data-mix-font]').forEach(button => button.addEventListener('click', () => {
        mixState[mixState.selecting] = button.dataset.mixFont;
        saveMixLocal();
        closeMixPicker();
        renderMixPanel(app);
    }));
}

async function loadMixConfig(app) {
    loadMixLocal();
    try {
        const output = await rawShell(`sh ${quote(MIX_BRIDGE)} config`);
        const result = parseJson(output);
        if (result.status === 'ok' && result.data) {
            mixState.enabled = Boolean(result.data.enabled);
            if (result.data.cjk) mixState.cjk = result.data.cjk;
            if (result.data.latin) mixState.latin = result.data.latin;
            if (result.data.digit) mixState.digit = result.data.digit;
            if (mixState.enabled) app.currentFont = 'mix';
        }
    } catch (error) { console.warn('[洛书] 字体组合状态读取失败', error); }
    mixState.initialized = true;
    ensureMixDefaults(app);
    renderMixPanel(app);
    if (app.currentFont === 'mix') { renderMixedCurrent(app); updateEngineCopy(app); }
}

async function waitForMixTask(taskId, timeoutMs = 540000) {
    const started = Date.now();
    let interval = 850;
    while (Date.now() - started < timeoutMs) {
        await sleep(interval);
        interval = Math.min(1700, interval + 120);
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} status ${quote(taskId)}`));
        if (result.status !== 'ok' || !result.data) continue;
        if (result.data.progress?.message) setProgress(true, result.data.progress.message, `${Number(result.data.progress.percent || 0)}% · 耗时取决于中文字体体积`);
        if (result.data.state === 'success' || result.data.state === 'failed') return result.data;
    }
    throw new Error('字体组合确认超时，后台任务可能仍在继续');
}

function finishMix(app, status, recovered = false) {
    localStorage.removeItem(MIX_PENDING_KEY);
    mixState.enabled = true;
    if (status?.cjk) mixState.cjk = status.cjk;
    if (status?.latin) mixState.latin = status.latin;
    if (status?.digit) mixState.digit = status.digit;
    saveMixLocal();
    app.applyFontData({ current: 'mix', fonts: app.fonts, stats: app.stats });
    app.saveLastSwitchResult({ status: 'success', font: '完整复合字体', time: Date.now(), message: status?.message || '' });
    app.textRebootRequired = true;
    app.pendingFont = null;
    app.updateRebootUI();
    app.renderList();
    renderMixPanel(app);
    renderMixedCurrent(app);
    updateEngineCopy(app);
    setProgress(false);
    app.showToast(recovered ? '✓ 已确认字体组合' : '✓ 字体组合已准备，重启后生效');
    app.showApplyDone('字体组合', mixSummary(app, ' / '));
}

async function applyFontMix(app) {
    if (app.textRebootRequired) { app.showToast('本次开机已更改文字字体，请先重启手机'); return; }
    if (app.isSwitching) { app.showToast('字体任务正在进行中'); return; }
    ensureMixDefaults(app);
    if (!mixState.cjk || !mixState.latin || !mixState.digit) { app.showToast('请先选择三种字体'); return; }
    app.isSwitching = true;
    document.body.classList.add('switching');
    renderMixPanel(app);
    setProgress(true, '正在启动复合字体任务', '后台任务已启动，即将显示真实进度');
    try {
        await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
        const result = parseJson(await rawShell(`sh ${quote(MIX_BRIDGE)} start ${quote(mixState.cjk)} ${quote(mixState.latin)} ${quote(mixState.digit)}`));
        if (result.status !== 'ok') throw new Error(result.message || '无法启动字体组合任务');
        const taskId = result.data?.task;
        if (!taskId) throw new Error('组合任务 ID 缺失');
        localStorage.setItem(MIX_PENDING_KEY, JSON.stringify({ task: taskId, started: Date.now(), cjk: mixState.cjk, latin: mixState.latin, digit: mixState.digit }));
        const status = await waitForMixTask(taskId);
        if (status.state !== 'success') throw new Error(status.message || '字体组合失败');
        finishMix(app, status, false);
    } catch (error) {
        const message = String(error?.message || error);
        setProgress(false);
        if (/超时|后台任务/.test(message) && localStorage.getItem(MIX_PENDING_KEY)) app.showToast('组合仍在后台处理，重新进入 WebUI 会自动确认');
        else { localStorage.removeItem(MIX_PENDING_KEY); app.saveLastSwitchResult({ status: 'failed', font: '完整复合字体', time: Date.now(), message }); app.showToast('组合失败: ' + message); }
    } finally {
        app.isSwitching = false;
        document.body.classList.remove('switching');
        renderMixPanel(app);
    }
}

async function recoverPendingMix(app) {
    let pending;
    try { pending = JSON.parse(localStorage.getItem(MIX_PENDING_KEY) || 'null'); }
    catch (_) { localStorage.removeItem(MIX_PENDING_KEY); return; }
    if (!pending?.task) return;
    if (Date.now() - Number(pending.started || 0) > 900000) { localStorage.removeItem(MIX_PENDING_KEY); return; }
    mixState.cjk = pending.cjk || mixState.cjk; mixState.latin = pending.latin || mixState.latin; mixState.digit = pending.digit || mixState.digit;
    setProgress(true, '正在确认字体组合', '后台任务已继续执行');
    try {
        const status = await waitForMixTask(pending.task, 240000);
        if (status.state === 'success') finishMix(app, status, true);
        else throw new Error(status.message || '字体组合失败');
    } catch (error) {
        setProgress(false);
        if (/超时|暂无|不存在/.test(String(error?.message || error))) app.showToast('后台组合任务尚未确认，可稍后重新进入查看');
        else { localStorage.removeItem(MIX_PENDING_KEY); app.showToast('组合失败: ' + String(error?.message || error)); }
    }
}

function finishSwitch(app, fontId, status, recovered = false) {
    localStorage.removeItem(PENDING_KEY);
    mixState.enabled = false;
    app.applyFontData({ current: fontId, fonts: app.fonts, stats: app.stats });
    app.recordUsage(fontId);
    const displayName = fontId === 'default' ? '系统默认字体' : fontName(app, fontId);
    app.saveLastSwitchResult({ status: 'success', font: displayName, time: Date.now(), message: status?.message || '' });
    app.textRebootRequired = true;
    app.pendingFont = null;
    app.updateRebootUI();
    app.renderList();
    renderMixPanel(app);
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
    if (Date.now() - Number(pending.started || 0) > 900000) { localStorage.removeItem(PENDING_KEY); return; }
    setProgress(true, '正在确认上次切换', '字体任务已在后台继续执行');
    try {
        const status = await app.waitForSwitchTask(pending.task, 240000);
        if (status.state === 'success') finishSwitch(app, pending.fontId, status, true);
        else throw new Error(status.message || '字体应用失败');
    } catch (error) {
        setProgress(false);
        if (/超时|暂无|不存在/.test(String(error?.message || error))) app.showToast('后台任务尚未确认，可稍后重新进入查看');
        else { localStorage.removeItem(PENDING_KEY); app.saveLastSwitchResult({ status: 'failed', font: pending.fontId, time: Date.now(), message: String(error?.message || error) }); app.showToast('切换失败: ' + String(error?.message || error)); }
    }
}

function simplifyUi(app) {
    document.documentElement.classList.add('luoshu-v14');
    document.querySelectorAll('#stabilityRescueButton,#stabilityModal,#openStabilityBtn').forEach(node => node.remove());
    const subtitle = document.querySelector('#helpModal .more-heading > p');
    if (subtitle) subtitle.textContent = '外观、字体组合与系统界面';
    const guide = document.querySelector('.guide-group');
    if (guide) {
        const second = guide.querySelectorAll('.guide-item')[1];
        if (second) second.innerHTML = '<b>2</b><span><strong>选择或组合</strong><small>可整套切换，也可分别选择中文、英文和数字</small></span>';
    }
    const settings = document.querySelector('#helpModal .more-group');
    if (settings && !document.getElementById('openFontMixBtn')) {
        const row = document.createElement('button');
        row.id = 'openFontMixBtn'; row.type = 'button'; row.className = 'setting-row mix-setting-row';
        row.innerHTML = '<span class="setting-icon mix"><b>中</b><i>Aa</i></span><span class="setting-copy"><strong>字体组合</strong><small>中文为完整基底，英文与数字替换字形</small></span><svg class="setting-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>';
        document.getElementById('themeToggleBtn')?.insertAdjacentElement('afterend', row);
        row.addEventListener('click', () => {
            document.getElementById('helpModal')?.classList.remove('show');
            document.body.classList.remove('modal-open');
            setTimeout(() => document.getElementById('fontMixPanel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
        });
    }
    injectMixPanel(app);
}

function patchApp() {
    const app = window.App;
    if (!app || app.__v14Patched) return false;
    app.__v14Patched = true;

    // v14 不再提供 Emoji 前端入口，启动时也不扫描 Emoji 目录。
    app.loadEmojis = async function() { this.currentEmoji = 'default'; this.emojis = []; };
    app.renderEmojis = function() {};

    const originalExecShell = app.execShell.bind(app);
    app.execShell = function(command) { return originalExecShell(normalizeManagerCommand(command)); };

    const originalApplyFontData = app.applyFontData.bind(app);
    app.applyFontData = function(data, persist = true) {
        originalApplyFontData(data, persist);
        if (mixState.initialized) { renderMixPanel(this); if (this.currentFont === 'mix') renderMixedCurrent(this); }
    };

    const originalRenderCurrent = app.renderCurrent.bind(app);
    app.renderCurrent = function() {
        if (!renderMixedCurrent(this)) originalRenderCurrent();
        updateEngineCopy(this);
    };

    app.waitForSwitchTask = async function(taskId, timeoutMs = 60000) {
        const started = Date.now();
        let interval = 850;
        while (Date.now() - started < timeoutMs) {
            await sleep(interval);
            interval = Math.min(1600, interval + 120);
            const result = parseJson(await rawShell(`sh ${quote(SWITCH_BRIDGE)} status ${quote(taskId)}`));
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
            const result = parseJson(await rawShell(`sh ${quote(SWITCH_BRIDGE)} start ${quote(fontId)}`));
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
            if (/超时|后台任务/.test(message) && localStorage.getItem(PENDING_KEY)) this.showToast('字体仍在后台处理，重新进入 WebUI 会自动确认');
            else { localStorage.removeItem(PENDING_KEY); this.saveLastSwitchResult({ status: 'failed', font: fontId === 'default' ? '系统默认字体' : fontId, time: Date.now(), message }); this.showToast('切换失败: ' + message); }
        } finally {
            this.isSwitching = false;
            document.body.classList.remove('switching');
            renderMixPanel(this);
        }
    };

    const originalInit = app.init.bind(app);
    app.init = async function() {
        await originalInit();
        simplifyUi(this);
        await loadMixConfig(this);
        updateEngineCopy(this);
        setTimeout(() => recoverPending(this), 160);
        setTimeout(() => recoverPendingMix(this), 260);
    };

    return true;
}

function removeLateStabilityUi() {
    const observer = new MutationObserver(() => document.querySelectorAll('#stabilityRescueButton,#stabilityModal,#openStabilityBtn').forEach(node => node.remove()));
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 6000);
}

if (!patchApp()) {
    const timer = setInterval(() => { if (patchApp()) clearInterval(timer); }, 20);
    setTimeout(() => clearInterval(timer), 3000);
}
removeLateStabilityUi();
