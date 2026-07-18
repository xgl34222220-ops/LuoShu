// 洛书 v14.2 Alpha6 — 工作台与概览共用的完整可变轴控件
// 可变字体显示全部 fvar 轴；静态多字重只显示真实档位；单字重明确固定状态。

const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';
const PRESET_KEY = 'luoshu_v142_mix_presets';
const SLOT_CONFIG = {
    cjk: { selectId: 'presetCjk', label: '中文', sample: '中文字体', mark: '中' },
    latin: { selectId: 'presetLatin', label: '英文', sample: 'LuoShu Aa', mark: 'Aa' },
    digit: { selectId: 'presetDigit', label: '数字', sample: '0123456789', mark: '123' },
};
const ROLE_VALUES = { thin: 100, light: 300, regular: 400, medium: 500, semibold: 600, bold: 700, black: 900 };
const ROLE_LABELS = { thin: '极细 100', light: '细体 300', regular: '常规 400', medium: '中等 500', semibold: '半粗 600', bold: '粗体 700', black: '特粗 900' };
const AXIS_NAMES = { wght: '字重', wdth: '字宽', slnt: '倾斜', ital: '斜体开关', opsz: '光学尺寸', GRAD: '笔画等级', XTRA: '横向扩展', YTAS: '上升部', YTDE: '下降部', YTFI: '数字高度', YTLC: '小写高度', YTUC: '大写高度' };
let renderToken = 0;
let renderScheduled = false;

function app() { return window.App; }
function clamp(value, min, max, fallback) {
    const number = Number(value);
    return Number.isFinite(number) ? Math.max(min, Math.min(max, number)) : fallback;
}
function formatNumber(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return '0';
    return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}
function parseAxisSpec(value) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
        return Object.fromEntries(Object.entries(value).filter(([tag, number]) => tag && Number.isFinite(Number(number))).map(([tag, number]) => [String(tag), Number(number)]));
    }
    const result = {};
    String(value || '').split(',').forEach(item => {
        const [tag, raw] = item.split('=', 2);
        const number = Number(raw);
        if (tag?.trim() && Number.isFinite(number)) result[tag.trim()] = number;
    });
    return result;
}
function serializeAxes(value) {
    return Object.entries(parseAxisSpec(value)).sort(([a], [b]) => a.localeCompare(b)).map(([tag, number]) => `${tag}=${formatNumber(number)}`).join(',');
}
function axesKey(slot) { return `${slot}Axes`; }
function legacyWeightKey(slot) { return `${slot}Weight`; }
function normalizeState(value = {}) {
    const state = {
        enabled: Boolean(value.enabled),
        cjk: String(value.cjk || ''), latin: String(value.latin || ''), digit: String(value.digit || ''),
    };
    Object.keys(SLOT_CONFIG).forEach(slot => {
        const axes = parseAxisSpec(value[axesKey(slot)]);
        if (!Object.prototype.hasOwnProperty.call(axes, 'wght')) axes.wght = clamp(value[legacyWeightKey(slot)], 1, 1000, 400);
        state[axesKey(slot)] = axes;
        state[legacyWeightKey(slot)] = Math.round(clamp(axes.wght, 1, 1000, 400));
    });
    return state;
}
function readState() {
    try { return normalizeState(JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null') || {}); }
    catch (_) { return normalizeState({}); }
}
function writeState(next = {}) {
    const current = readState();
    const merged = normalizeState({ ...current, ...next });
    const serialized = JSON.stringify(merged);
    if (localStorage.getItem(MIX_LOCAL_KEY) === serialized) return merged;
    localStorage.setItem(MIX_LOCAL_KEY, serialized);
    window.dispatchEvent(new CustomEvent('luoshu-axis-state-change', { detail: merged }));
    return merged;
}
function readPresets() {
    try { const value = JSON.parse(localStorage.getItem(PRESET_KEY) || '[]'); return Array.isArray(value) ? value : []; }
    catch (_) { return []; }
}
function writePresets(value) { localStorage.setItem(PRESET_KEY, JSON.stringify(value.slice(0, 20))); }
function fontById(id) { return (app()?.fonts || []).find(font => font?.id === id); }
function fontFamily(font) {
    if (!font) return 'sans-serif';
    app()?.injectFontFace?.(font);
    const safe = app()?.safeId?.(font.id) || String(font.id || '').replace(/[^a-zA-Z0-9]/g, '_');
    return `'preview_${safe}', sans-serif`;
}
function staticWeights(font) {
    const roles = Array.isArray(font?.weights) ? font.weights.filter(role => ROLE_VALUES[role]) : [];
    return [...new Set(roles)].sort((a, b) => ROLE_VALUES[a] - ROLE_VALUES[b]);
}
function nearest(values, target) {
    if (!values.length) return 400;
    return values.reduce((best, value) => Math.abs(value - target) < Math.abs(best - target) ? value : best, values[0]);
}
async function describeModel(font) {
    if (!font) return { type: 'none', axes: [] };
    if (font.variable) {
        try {
            const result = await app()?.analyzeFont?.(font);
            const axes = (result?.variable?.axes || []).map(axis => ({
                tag: String(axis.tag || '').trim(),
                min: Number(axis.min), max: Number(axis.max), default: Number(axis.default),
            })).filter(axis => axis.tag && Number.isFinite(axis.min) && Number.isFinite(axis.max) && Number.isFinite(axis.default) && axis.max >= axis.min);
            if (axes.length) return { type: 'variable', axes };
        } catch (_) { /* 按静态结构降级 */ }
    }
    const roles = staticWeights(font);
    if (roles.length > 1) return { type: 'static', roles, values: roles.map(role => ROLE_VALUES[role]) };
    if (roles.length === 1) return { type: 'fixed', role: roles[0], value: ROLE_VALUES[roles[0]] };
    return { type: 'fixed', role: 'regular', value: 400 };
}
function currentSelectionFromDom() {
    const value = readState();
    Object.entries(SLOT_CONFIG).forEach(([slot, config]) => {
        const select = document.getElementById(config.selectId);
        if (select) value[slot] = select.value || '';
    });
    return value;
}
function stepForAxis(axis) {
    if (axis.tag === 'ital') return 1;
    const span = axis.max - axis.min;
    if (span <= 2) return 0.01;
    if (span <= 20) return 0.1;
    return Math.max(1, Math.round(span / 200));
}
function previewSettings(axes) {
    return Object.entries(axes).map(([tag, value]) => `"${tag}" ${Number(value)}`).join(', ');
}
function axisControlHtml(slot, axis, value) {
    const name = AXIS_NAMES[axis.tag] || '自定义轴';
    const step = stepForAxis(axis);
    return `<label class="axis-editor-row"><span><b>${axis.tag}</b><small>${name}</small><output data-axis-output="${slot}:${axis.tag}">${formatNumber(value)}</output></span><input type="range" data-axis-input="${slot}:${axis.tag}" min="${axis.min}" max="${axis.max}" step="${step}" value="${value}"><i><em>${formatNumber(axis.min)}</em><em>默认 ${formatNumber(axis.default)}</em><em>${formatNumber(axis.max)}</em></i></label>`;
}
function createControlHost(surface, slot) {
    if (surface === 'workbench') {
        const select = document.getElementById(SLOT_CONFIG[slot].selectId);
        const label = select?.closest('label');
        if (!select || !label) return null;
        let host = label.querySelector(`[data-axis-control="${slot}"]`);
        if (!host) {
            host = document.createElement('div'); host.className = 'preset-weight-control'; host.dataset.axisControl = slot;
            select.insertAdjacentElement('afterend', host);
        }
        return { host, fontId: select.value || '' };
    }
    const panel = document.getElementById('mixAxisPanel');
    const card = panel?.querySelector(`[data-overview-axis-slot="${slot}"]`);
    if (!card) return null;
    return { host: card.querySelector('.overview-axis-body'), fontId: readState()[slot] || '' };
}
function syncPreview(host, font, axes) {
    const preview = host.querySelector('.preset-weight-preview');
    if (!preview || !font) return;
    preview.style.fontFamily = fontFamily(font);
    preview.style.fontWeight = String(Math.round(Number(axes.wght || 400)));
    preview.style.fontVariationSettings = previewSettings(axes);
}
async function renderControl(surface, slot, token) {
    const context = createControlHost(surface, slot);
    if (!context?.host) return;
    const { host, fontId } = context;
    const font = fontById(fontId);
    if (!font) { host.innerHTML = '<div class="preset-weight-empty">选择字体后显示可调参数</div>'; return; }
    host.innerHTML = '<div class="preset-weight-loading"><i></i><span>正在读取字体轴…</span></div>';
    const model = await describeModel(font);
    if (token !== renderToken || !host.isConnected) return;
    const state = readState();
    const key = axesKey(slot);
    let axes = { ...state[key] };
    if (model.type === 'variable') {
        const normalized = {};
        model.axes.forEach(axis => { normalized[axis.tag] = clamp(axes[axis.tag], axis.min, axis.max, axis.default); });
        axes = normalized;
        writeState({ [slot]: font.id, [key]: axes });
        host.innerHTML = `<div class="preset-weight-head"><span><b>${SLOT_CONFIG[slot].label}可变轴</b><small>${model.axes.length} 个轴都会写入最终组合字体</small></span><output>${formatNumber(axes.wght ?? model.axes[0]?.default ?? 0)}</output></div><div class="axis-editor-list">${model.axes.map(axis => axisControlHtml(slot, axis, axes[axis.tag])).join('')}</div><div class="preset-weight-preview">${SLOT_CONFIG[slot].sample}</div>`;
        const headline = host.querySelector('.preset-weight-head output');
        host.querySelectorAll('[data-axis-input]').forEach(slider => slider.addEventListener('input', event => {
            const [, tag] = event.target.dataset.axisInput.split(':');
            const axis = model.axes.find(item => item.tag === tag);
            axes[tag] = clamp(event.target.value, axis.min, axis.max, axis.default);
            const output = host.querySelector(`[data-axis-output="${slot}:${tag}"]`);
            if (output) output.textContent = formatNumber(axes[tag]);
            if (headline) headline.textContent = formatNumber(axes.wght ?? axes[tag]);
            writeState({ [slot]: font.id, [key]: axes });
            syncPreview(host, font, axes);
        }));
        syncPreview(host, font, axes);
        return;
    }
    if (model.type === 'static') {
        const value = nearest(model.values, Number(axes.wght || 400));
        axes = { wght: value };
        writeState({ [slot]: font.id, [key]: axes });
        host.innerHTML = `<div class="preset-weight-head"><span><b>${SLOT_CONFIG[slot].label}字重</b><small>静态家族 · 只能选择真实文件档位</small></span><output>${value}</output></div><select class="preset-static-weight" aria-label="${SLOT_CONFIG[slot].label}静态字重">${model.roles.map(role => `<option value="${ROLE_VALUES[role]}" ${ROLE_VALUES[role] === value ? 'selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}</select><div class="preset-weight-preview">${SLOT_CONFIG[slot].sample}</div>`;
        host.querySelector('select')?.addEventListener('change', event => {
            axes = { wght: Number(event.target.value) };
            host.querySelector('output').textContent = String(axes.wght);
            writeState({ [slot]: font.id, [key]: axes });
            syncPreview(host, font, axes);
        });
        syncPreview(host, font, axes);
        return;
    }
    const value = model.value || 400;
    axes = { wght: value };
    writeState({ [slot]: font.id, [key]: axes });
    host.innerHTML = `<div class="preset-weight-head fixed"><span><b>${SLOT_CONFIG[slot].label}字重</b><small>单一静态字重，不存在连续轴</small></span><output>${value}</output></div><div class="preset-weight-fixed">固定为 ${ROLE_LABELS[model.role] || value}</div><div class="preset-weight-preview">${SLOT_CONFIG[slot].sample}</div>`;
    syncPreview(host, font, axes);
}
function ensureOverviewPanel() {
    const slots = document.querySelector('#fontMixPanel .mix-slots');
    if (!slots || document.getElementById('mixAxisPanel')) return;
    const panel = document.createElement('div');
    panel.id = 'mixAxisPanel'; panel.className = 'mix-axis-panel';
    panel.innerHTML = Object.entries(SLOT_CONFIG).map(([slot, config]) => `<section class="overview-axis-card ${slot}" data-overview-axis-slot="${slot}"><header><span>${config.mark}</span><div><b>${config.label}参数</b><small>与工作台实时同步</small></div></header><div class="overview-axis-body"><div class="preset-weight-loading"><i></i><span>正在读取字体轴…</span></div></div></section>`).join('');
    slots.insertAdjacentElement('afterend', panel);
}
function renderPresetBadges() {
    const presets = readPresets();
    document.querySelectorAll('.preset-card').forEach((card, index) => {
        const item = presets[index]; if (!item) return;
        let badge = card.querySelector('.preset-card-weights');
        if (!badge) { badge = document.createElement('div'); badge.className = 'preset-card-weights'; card.querySelector('.preset-card-slots')?.insertAdjacentElement('afterend', badge); }
        badge.innerHTML = Object.entries(SLOT_CONFIG).map(([slot, config]) => {
            const axes = parseAxisSpec(item[axesKey(slot)] || { wght: item[legacyWeightKey(slot)] || 400 });
            const summary = Object.entries(axes).map(([tag, value]) => `${tag} ${formatNumber(value)}`).join(' · ');
            return `<span>${config.mark} ${summary}</span>`;
        }).join('');
    });
}
function scheduleRender() {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(async () => {
        renderScheduled = false;
        document.querySelectorAll('.workbench-version').forEach(element => { element.textContent = 'v14.2 Alpha6'; });
        ensureOverviewPanel();
        const token = ++renderToken;
        Object.entries(SLOT_CONFIG).forEach(([slot, config]) => {
            const select = document.getElementById(config.selectId);
            if (select && !select.dataset.axisBound) {
                select.dataset.axisBound = '1';
                select.addEventListener('change', () => {
                    const state = readState();
                    writeState({ [slot]: select.value || '', [axesKey(slot)]: {} });
                    renderControl('workbench', slot, ++renderToken);
                });
            }
        });
        const tasks = [];
        Object.keys(SLOT_CONFIG).forEach(slot => {
            if (document.getElementById(SLOT_CONFIG[slot].selectId)) tasks.push(renderControl('workbench', slot, token));
            if (document.getElementById('mixAxisPanel')) tasks.push(renderControl('overview', slot, token));
        });
        await Promise.all(tasks);
        renderPresetBadges();
    });
}
function persistPresetAxes(nameHint, snapshot) {
    const presets = readPresets(); if (!presets.length) return;
    let item = presets.find(preset => preset.name === nameHint) || presets[0];
    Object.keys(SLOT_CONFIG).forEach(slot => {
        item[axesKey(slot)] = snapshot[axesKey(slot)];
        item[legacyWeightKey(slot)] = Math.round(Number(snapshot[axesKey(slot)]?.wght || 400));
    });
    writePresets(presets); scheduleRender();
}
function bindDelegatedEvents() {
    document.addEventListener('click', event => {
        const save = event.target?.closest?.('#savePresetBtn');
        if (save) {
            const snapshot = currentSelectionFromDom();
            const inputName = (document.getElementById('presetName')?.value || '').trim();
            const fallbackName = `${fontById(snapshot.cjk)?.name || snapshot.cjk || '字体'}组合`;
            setTimeout(() => persistPresetAxes(inputName || fallbackName, snapshot), 0);
            return;
        }
        const load = event.target?.closest?.('[data-preset-load],[data-preset-apply]');
        if (load) {
            const index = Number(load.dataset.presetLoad ?? load.dataset.presetApply);
            const item = readPresets()[index];
            if (item) {
                const patch = { cjk: item.cjk, latin: item.latin, digit: item.digit };
                Object.keys(SLOT_CONFIG).forEach(slot => { patch[axesKey(slot)] = item[axesKey(slot)] || { wght: item[legacyWeightKey(slot)] || 400 }; });
                writeState(patch); setTimeout(scheduleRender, 0);
            }
        }
    }, true);
}
function installStyles() {
    if (document.getElementById('workbenchWeightStyles')) return;
    const link = document.createElement('link'); link.id = 'workbenchWeightStyles'; link.rel = 'stylesheet'; link.href = './workbench_weight_extension.css?v=14206'; document.head.appendChild(link);
}
function initialize() {
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
}
window.LuoShuAxisUI = Object.freeze({ readState, writeState, parseAxisSpec, serializeAxes, scheduleRender });
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
