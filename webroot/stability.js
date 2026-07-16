// 洛书 v13.5 Stable - 独立自救面板
// 不依赖 app.js；主界面脚本异常时仍可清理缓存、修复权限和导出报告。
import { exec } from './kernelsu.js';

const SCRIPT = '/data/adb/modules/LuoShu/common/stability.sh';
const STYLE_VERSION = '13500';
if (!document.querySelector('link[data-luoshu-stability]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `stability.css?v=${STYLE_VERSION}`;
    link.dataset.luoshuStability = 'true';
    document.head.appendChild(link);
}
const UI_SCAN_KEY = 'luoshu_stability_ui_scan_v1';
let uiScanStartedAt = Date.now();
let panelBusy = false;

function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

async function run(command) {
    const result = await exec(`sh "${SCRIPT}" ${command}`);
    const stdout = String(result && result.stdout || '');
    const stderr = String(result && result.stderr || '');
    const output = stdout || stderr;
    const line = output.split('\n').find(item => item.trim().startsWith('{'));
    if (!line) throw new Error(stderr.trim() || `命令没有返回有效结果（${result && result.errno}）`);
    let parsed;
    try { parsed = JSON.parse(line.trim()); }
    catch (_) { throw new Error('自救组件返回格式异常'); }
    if (parsed.status !== 'ok') throw new Error(parsed.message || '操作失败');
    return parsed;
}

function notify(message, tone = 'normal') {
    let el = document.getElementById('stabilityToast');
    if (!el) {
        el = document.createElement('div');
        el.id = 'stabilityToast';
        el.className = 'stability-toast';
        document.body.appendChild(el);
    }
    el.textContent = message;
    el.dataset.tone = tone;
    el.classList.add('show');
    clearTimeout(notify.timer);
    notify.timer = setTimeout(() => el.classList.remove('show'), 2800);
}

function formatDuration(ms) {
    const value = Number(ms) || 0;
    if (!value) return '尚未测试';
    if (value < 1000) return `${value} ms`;
    return `${(value / 1000).toFixed(value < 10000 ? 1 : 0)} 秒`;
}

function formatTime(seconds) {
    const value = Number(seconds) || 0;
    if (!value) return '无记录';
    try { return new Date(value * 1000).toLocaleString(); }
    catch (_) { return String(value); }
}

function readUiScan() {
    try { return JSON.parse(localStorage.getItem(UI_SCAN_KEY) || 'null'); }
    catch (_) { return null; }
}

function clearWebCaches() {
    const exact = [
        'luoshu_font_data_v2', 'luoshu_font_analysis_v2',
        'luoshu_last_switch_result_v1'
    ];
    exact.forEach(key => localStorage.removeItem(key));
    const dynamic = [];
    for (let index = 0; index < localStorage.length; index += 1) {
        const key = localStorage.key(index);
        if (key && (key.startsWith('luoshu_font_data_') || key.startsWith('luoshu_font_analysis_'))) dynamic.push(key);
    }
    dynamic.forEach(key => localStorage.removeItem(key));
}

function injectUi() {
    if (document.getElementById('stabilityRescueButton')) return;
    const button = document.createElement('button');
    button.id = 'stabilityRescueButton';
    button.className = 'stability-rescue-button';
    button.type = 'button';
    button.setAttribute('aria-label', '打开洛书自救');
    button.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M12 3l7 3v5c0 4.7-2.8 8.1-7 10-4.2-1.9-7-5.3-7-10V6l7-3z"/><path d="M9 12l2 2 4-5"/></svg><span>自救</span>';
    document.body.appendChild(button);

    const modal = document.createElement('div');
    modal.id = 'stabilityModal';
    modal.className = 'stability-modal';
    modal.innerHTML = `
        <div class="stability-sheet" role="dialog" aria-modal="true" aria-labelledby="stabilityTitle">
            <div class="stability-handle"></div>
            <header class="stability-head">
                <div class="stability-head-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l7 3v5c0 4.7-2.8 8.1-7 10-4.2-1.9-7-5.3-7-10V6l7-3z"/><path d="M9 12l2 2 4-5"/></svg></div>
                <div><h2 id="stabilityTitle">洛书自救</h2><p>独立于字体库运行，页面卡住时也能使用</p></div>
                <button class="stability-close" id="stabilityClose" type="button" aria-label="关闭">×</button>
            </header>
            <div class="stability-content">
                <section class="stability-summary" id="stabilitySummary">
                    <div class="stability-loading"><i></i><span>正在检查模块状态…</span></div>
                </section>
                <section class="stability-actions">
                    <button type="button" data-stability-action="scan"><b>重建字体索引</b><small>清理列表缓存并记录真实扫描耗时</small></button>
                    <button type="button" data-stability-action="cache"><b>清除 WebUI 缓存</b><small>处理一直加载、显示旧数据等问题</small></button>
                    <button type="button" data-stability-action="permissions"><b>修复脚本权限</b><small>恢复模块脚本与公开目录权限</small></button>
                    <button type="button" class="rollback" data-stability-action="rollback"><b>恢复上一个稳定配置</b><small>恢复文字、Emoji 和字体粗细</small></button>
                    <button type="button" data-stability-action="report"><b>生成自救报告</b><small>保存 ROM、扫描和最近日志信息</small></button>
                    <button type="button" data-stability-action="refresh"><b>重新检测状态</b><small>刷新 ROM、路径和模块状态</small></button>
                </section>
                <div class="stability-note">回滚会调用正常的安全切换流程。若本次开机已经切换过字体，请先完整重启，再执行回滚。</div>
            </div>
        </div>`;
    document.body.appendChild(modal);

    button.addEventListener('click', openPanel);
    modal.addEventListener('click', event => { if (event.target === modal) closePanel(); });
    modal.querySelector('#stabilityClose').addEventListener('click', closePanel);
    modal.querySelectorAll('[data-stability-action]').forEach(item => item.addEventListener('click', () => handleAction(item.dataset.stabilityAction, item)));

    const reportRow = document.getElementById('generateReportBtn');
    if (reportRow && !document.getElementById('openStabilityBtn')) {
        const row = document.createElement('button');
        row.className = 'setting-row';
        row.id = 'openStabilityBtn';
        row.type = 'button';
        row.innerHTML = '<span class="setting-icon green"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M12 3l7 3v5c0 4.7-2.8 8.1-7 10-4.2-1.9-7-5.3-7-10V6l7-3z"/><path d="M9 12l2 2 4-5"/></svg></span><span class="setting-copy"><strong>自救与稳定性</strong><small>缓存、权限、扫描测试和配置回滚</small></span><svg class="setting-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18l6-6-6-6"/></svg>';
        reportRow.insertAdjacentElement('afterend', row);
        row.addEventListener('click', () => {
            document.getElementById('helpModal')?.classList.remove('show');
            openPanel();
        });
    }
}

function openPanel() {
    const modal = document.getElementById('stabilityModal');
    if (!modal) return;
    modal.classList.add('show');
    document.body.classList.add('stability-open');
    loadStatus();
}

function closePanel() {
    document.getElementById('stabilityModal')?.classList.remove('show');
    document.body.classList.remove('stability-open');
}

function healthItem(ok, title, detail) {
    return `<div class="stability-health ${ok ? 'ok' : 'bad'}"><i>${ok ? '✓' : '!'}</i><span><b>${escapeHtml(title)}</b><small>${escapeHtml(detail)}</small></span></div>`;
}

function renderStatus(data) {
    const box = document.getElementById('stabilitySummary');
    if (!box) return;
    const previous = data.previousFont
        ? `${data.previousFont}${data.previousEmoji && data.previousEmoji !== 'default' ? ` + ${data.previousEmoji}` : ''}`
        : '尚未建立';
    const shellScan = data.lastScanResult === 'ok'
        ? `${formatDuration(data.lastScanMs)} · ${formatTime(data.lastScanAt)}`
        : (data.lastScanResult === 'failed' ? `失败 · ${formatDuration(data.lastScanMs)}` : '尚未运行');
    const uiScan = readUiScan();
    const configCount = String(data.fontConfigs || '').split(',').filter(Boolean).length;
    box.innerHTML = `
        <div class="stability-version"><span>稳定性中心</span><b>${escapeHtml(data.version || 'LuoShu')}</b></div>
        <div class="stability-health-grid">
            ${healthItem(Boolean(data.moduleReadable), '模块目录', data.moduleReadable ? '可读取' : '无法读取 module.prop')}
            ${healthItem(Boolean(data.scriptsExecutable), '脚本权限', data.scriptsExecutable ? '正常' : '需要修复')}
            ${healthItem(Boolean(data.fontsReadable), '字体目录', data.fontsReadable ? `${data.fontFiles || 0} 个文字字体 · ${data.emojiFiles || 0} 个 Emoji` : '公开目录不可读取')}
            ${healthItem(data.lastScanResult !== 'failed', '字体扫描', shellScan)}
        </div>
        <div class="stability-info-grid">
            <div><small>自动识别 ROM</small><b>${escapeHtml(data.rom || '未知')}</b><span>Android ${escapeHtml(data.android || '?')} · SDK ${escapeHtml(data.sdk || '?')}</span></div>
            <div><small>Root 环境</small><b>${escapeHtml(data.root || '未知')}</b><span>检测到 ${configCount} 个系统字体配置</span></div>
            <div><small>当前配置</small><b>${escapeHtml(data.currentFont || 'default')}</b><span>Emoji：${escapeHtml(data.currentEmoji || 'default')} · 粗细偏移 ${escapeHtml(data.weight || '0')}</span></div>
            <div><small>上一个稳定配置</small><b>${escapeHtml(previous)}</b><span>${data.previousFont ? '可以一键回滚' : '完成一次字体切换并重启后自动建立'}</span></div>
        </div>
        <div class="stability-scan-meta"><span>WebUI 最近展示耗时</span><b>${uiScan ? formatDuration(uiScan.durationMs) : '无记录'}</b></div>`;
}

async function loadStatus() {
    const box = document.getElementById('stabilitySummary');
    if (box) box.innerHTML = '<div class="stability-loading"><i></i><span>正在检查模块状态…</span></div>';
    try {
        const result = await run('status');
        renderStatus(result.data || {});
    } catch (error) {
        if (box) box.innerHTML = `<div class="stability-fatal"><b>自救组件无法读取状态</b><span>${escapeHtml(error && error.message || error)}</span></div>`;
    }
}

async function handleAction(action, button) {
    if (panelBusy) return;
    if (action === 'rollback' && !window.confirm('确定恢复上一个稳定配置？任务完成后需要完整重启手机。')) return;
    panelBusy = true;
    const old = button.innerHTML;
    button.disabled = true;
    button.classList.add('busy');
    button.innerHTML = '<b>正在处理…</b><small>请不要重复点击</small>';
    try {
        let result;
        if (action === 'cache') {
            clearWebCaches();
            result = await run('clear_cache');
        } else if (action === 'scan') result = await run('scan_test');
        else if (action === 'permissions') result = await run('repair_permissions');
        else if (action === 'rollback') result = await run('rollback');
        else if (action === 'report') result = await run('report');
        else result = await run('status');
        notify(result.message || '操作完成', 'ok');
        await loadStatus();
        if (action === 'cache' || action === 'scan') {
            setTimeout(() => window.location.reload(), 700);
        }
    } catch (error) {
        notify(error && error.message || String(error), 'error');
    } finally {
        panelBusy = false;
        button.disabled = false;
        button.classList.remove('busy');
        button.innerHTML = old;
    }
}

function watchFontList() {
    const list = document.getElementById('fontList');
    if (!list) return;
    uiScanStartedAt = Date.now();
    const record = () => {
        const loading = list.querySelector('.loading, .skeleton-card, .analysis-loading');
        if (loading) return false;
        const durationMs = Date.now() - uiScanStartedAt;
        localStorage.setItem(UI_SCAN_KEY, JSON.stringify({ durationMs, finishedAt: Date.now() }));
        document.getElementById('stabilityRescueButton')?.classList.remove('attention');
        document.getElementById('stabilityStallHint')?.remove();
        return true;
    };
    const observer = new MutationObserver(() => record());
    observer.observe(list, { childList: true, subtree: true });
    record();
    document.getElementById('refreshBtn')?.addEventListener('click', () => { uiScanStartedAt = Date.now(); });
    setTimeout(() => {
        if (!list.querySelector('.loading, .skeleton-card, .analysis-loading')) return;
        document.getElementById('stabilityRescueButton')?.classList.add('attention');
        if (!document.getElementById('stabilityStallHint')) {
            const hint = document.createElement('button');
            hint.id = 'stabilityStallHint';
            hint.className = 'stability-stall-hint';
            hint.type = 'button';
            hint.innerHTML = '<b>字体库加载时间较长</b><span>打开自救面板检查缓存与扫描状态</span>';
            hint.addEventListener('click', openPanel);
            list.insertAdjacentElement('afterend', hint);
        }
    }, 18000);
}

function init() {
    injectUi();
    watchFontList();
    document.querySelectorAll('[data-module-version]').forEach(item => { item.textContent = 'v13.5 Stable'; });
    const badge = document.getElementById('engineVersion');
    if (badge) badge.textContent = 'v13.5 Stable';
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init, { once: true });
else init();
