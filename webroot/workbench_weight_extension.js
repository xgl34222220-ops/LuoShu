// 洛书 v14.2 Alpha2 — 组合页独立字重控件
// 可变字体显示连续 wght 滑块；静态多字重显示真实档位；单字重只显示固定状态。

const MIX_LOCAL_KEY = 'luoshu_v14_mix_selection';
const PRESET_KEY = 'luoshu_v142_mix_presets';
const SLOT_CONFIG = {
    cjk: { selectId: 'presetCjk', label: '中文', sample: '中文字体' },
    latin: { selectId: 'presetLatin', label: '英文', sample: 'LuoShu Aa' },
    digit: { selectId: 'presetDigit', label: '数字', sample: '0123456789' },
};
const ROLE_VALUES = { thin: 100, light: 300, regular: 400, medium: 500, semibold: 600, bold: 700, black: 900 };
const ROLE_LABELS = { thin: '极细 100', light: '细体 300', regular: '常规 400', medium: '中等 500', semibold: '半粗 600', bold: '粗体 700', black: '特粗 900' };
let renderToken = 0;
let renderScheduled = false;

function app() { return window.App; }
function clampWeight(value, fallback = 400) {
    const number = Number(value);
    if (!Number.isFinite(number)) return fallback;
    return Math.max(1, Math.min(1000, Math.round(number)));
}
function readState() {
    try {
        const value = JSON.parse(localStorage.getItem(MIX_LOCAL_KEY) || 'null') || {};
        return {
            cjk: String(value.cjk || ''), latin: String(value.latin || ''), digit: String(value.digit || ''),
            cjkWeight: clampWeight(value.cjkWeight, 400), latinWeight: clampWeight(value.latinWeight, 400), digitWeight: clampWeight(value.digitWeight, 400),
        };
    } catch (_) {
        return { cjk: '', latin: '', digit: '', cjkWeight: 400, latinWeight: 400, digitWeight: 400 };
    }
}
function writeState(next = {}) {
    const current = readState();
    const value = {
        ...current,
        ...next,
        cjkWeight: clampWeight(next.cjkWeight ?? current.cjkWeight, 400),
        latinWeight: clampWeight(next.latinWeight ?? current.latinWeight, 400),
        digitWeight: clampWeight(next.digitWeight ?? current.digitWeight, 400),
    };
    localStorage.setItem(MIX_LOCAL_KEY, JSON.stringify(value));
    return value;
}
function readPresets() {
    try {
        const value = JSON.parse(localStorage.getItem(PRESET_KEY) || '[]');
        return Array.isArray(value) ? value : [];
    } catch (_) { return []; }
}
function writePresets(value) { localStorage.setItem(PRESET_KEY, JSON.stringify(value.slice(0, 20))); }
function fontById(id) { return (app()?.fonts || []).find(font => font?.id === id); }
function fontFamily(font) {
    if (!font) return 'sans-serif';
    app()?.injectFontFace?.(font);
    const safe = app()?.safeId?.(font.id) || String(font.id || '').replace(/[^a-zA-Z0-9]/g, '_');
    return `'preview_${safe}', sans-serif`;
}
function weightKey(slot) { return `${slot}Weight`; }
function nearest(values, target) {
    if (!values.length) return 400;
    return values.reduce((best, value) => Math.abs(value - target) < Math.abs(best - target) ? value : best, values[0]);
}
function staticWeights(font) {
    const roles = Array.isArray(font?.weights) ? font.weights.filter(role => ROLE_VALUES[role]) : [];
    return [...new Set(roles)].sort((a, b) => ROLE_VALUES[a] - ROLE_VALUES[b]);
}
async function describeWeightModel(font) {
    if (!font) return { type: 'none', value: 400 };
    if (font.variable) {
        try {
            const result = await app()?.analyzeFont?.(font);
            const axis = (result?.variable?.axes || []).find(item => String(item.tag || '').trim() === 'wght');
            if (axis) {
                const min = Math.max(1, Math.ceil(Number(axis.min) || 1));
                const max = Math.min(1000, Math.floor(Number(axis.max) || 1000));
                const fallback = Math.max(min, Math.min(max, Math.round(Number(axis.default) || 400)));
                return { type: 'variable', min, max, fallback, axis };
            }
        } catch (_) { /* 后续按静态结构降级 */ }
    }
    const roles = staticWeights(font);
    if (roles.length > 1) return { type: 'static', roles, values: roles.map(role => ROLE_VALUES[role]), fallback: ROLE_VALUES[roles.includes('regular') ? 'regular' : roles[0]] };
    if (roles.length === 1) return { type: 'fixed', role: roles[0], value: ROLE_VALUES[roles[0]] };
    return { type: 'fixed', role: 'regular', value: 400 };
}
function currentSelectionFromDom() {
    const stored = readState();
    const value = { ...stored };
    Object.entries(SLOT_CONFIG).forEach(([slot, config]) => {
        const select = document.getElementById(config.selectId);
        if (select) value[slot] = select.value || '';
    });
    return value;
}
function updateStoredSelection(patch = {}) {
    const value = writeState({ ...currentSelectionFromDom(), ...patch });
    window.dispatchEvent(new CustomEvent('luoshu-weight-control-change', { detail: value }));
    return value;
}
function controlShell(select, slot) {
    const label = select.closest('label');
    if (!label) return null;
    let shell = label.querySelector(`[data-weight-control="${slot}"]`);
    if (!shell) {
        shell = document.createElement('div');
        shell.className = 'preset-weight-control';
        shell.dataset.weightControl = slot;
        select.insertAdjacentElement('afterend', shell);
    }
    return shell;
}
function syncPreview(shell, font, value, variable = false) {
    const preview = shell.querySelector('.preset-weight-preview');
    if (!preview || !font) return;
    preview.style.fontFamily = fontFamily(font);
    preview.style.fontWeight = String(value);
    preview.style.fontVariationSettings = variable ? `"wght" ${value}` : '';
}
async function renderSlotControl(slot, token) {
    const config = SLOT_CONFIG[slot];
    const select = document.getElementById(config.selectId);
    if (!select) return;
    const shell = controlShell(select, slot);
    if (!shell) return;
    const font = fontById(select.value);
    if (!font) {
        shell.innerHTML = '<div class="preset-weight-empty">选择字体后显示字重设置</div>';
        return;
    }
    shell.innerHTML = '<div class="preset-weight-loading"><i></i><span>正在读取字重结构…</span></div>';
    const model = await describeWeightModel(font);
    if (token !== renderToken || select.value !== font.id || !shell.isConnected) return;
    const state = readState();
    const key = weightKey(slot);
    let value = clampWeight(state[key], model.fallback || model.value || 400);
    if (model.type === 'variable') {
        value = Math.max(model.min, Math.min(model.max, value));
        writeState({ [slot]: font.id, [key]: value });
        const presets = [300, 400, 500, 600, 700].filter(item => item >= model.min && item <= model.max);
        shell.innerHTML = `
            <div class="preset-weight-head"><span><b>${config.label}字重</b><small>可变字体 · 连续调节</small></span><output>${value}</output></div>
            <input class="preset-weight-slider" type="range" min="${model.min}" max="${model.max}" step="10" value="${value}" aria-label="${config.label}字体字重">
            <div class="preset-weight-scale"><span>${model.min}</span><span>默认 ${Math.round(Number(model.axis.default) || 400)}</span><span>${model.max}</span></div>
            <div class="preset-weight-presets">${presets.map(item => `<button type="button" data-weight-value="${item}" class="${item === value ? 'active' : ''}">${item}</button>`).join('')}</div>
            <div class="preset-weight-preview">${config.sample}</div>`;
        const slider = shell.querySelector('input[type="range"]');
        const output = shell.querySelector('output');
        const sync = next => {
            const number = Math.max(model.min, Math.min(model.max, clampWeight(next, value)));
            slider.value = String(number); output.textContent = String(number);
            shell.querySelectorAll('[data-weight-value]').forEach(button => button.classList.toggle('active', Number(button.dataset.weightValue) === number));
            updateStoredSelection({ [slot]: font.id, [key]: number });
            syncPreview(shell, font, number, true);
        };
        slider.addEventListener('input', event => sync(event.target.value));
        shell.querySelectorAll('[data-weight-value]').forEach(button => button.addEventListener('click', () => sync(button.dataset.weightValue)));
        syncPreview(shell, font, value, true);
        return;
    }
    if (model.type === 'static') {
        value = nearest(model.values, value);
        writeState({ [slot]: font.id, [key]: value });
        shell.innerHTML = `
            <div class="preset-weight-head"><span><b>${config.label}字重</b><small>静态家族 · 选择真实文件档位</small></span><output>${value}</output></div>
            <select class="preset-static-weight" aria-label="${config.label}静态字重">${model.roles.map(role => `<option value="${ROLE_VALUES[role]}" ${ROLE_VALUES[role] === value ? 'selected' : ''}>${ROLE_LABELS[role]}</option>`).join('')}</select>
            <div class="preset-weight-preview">${config.sample}</div>`;
        const picker = shell.querySelector('select');
        picker.addEventListener('change', event => {
            const number = clampWeight(event.target.value, value);
            shell.querySelector('output').textContent = String(number);
            updateStoredSelection({ [slot]: font.id, [key]: number });
            syncPreview(shell, font, number, false);
        });
        syncPreview(shell, font, value, false);
        return;
    }
    value = model.value || 400;
    writeState({ [slot]: font.id, [key]: value });
    shell.innerHTML = `
        <div class="preset-weight-head fixed"><span><b>${config.label}字重</b><small>单一静态字重，无法连续调节</small></span><output>${value}</output></div>
        <div class="preset-weight-fixed">固定为 ${ROLE_LABELS[model.role] || value}</div>
        <div class="preset-weight-preview">${config.sample}</div>`;
    syncPreview(shell, font, value, false);
}
function renderPresetWeightBadges() {
    const presets = readPresets();
    document.querySelectorAll('.preset-card').forEach((card, index) => {
        const item = presets[index];
        if (!item) return;
        let badge = card.querySelector('.preset-card-weights');
        if (!badge) {
            badge = document.createElement('div');
            badge.className = 'preset-card-weights';
            card.querySelector('.preset-card-slots')?.insertAdjacentElement('afterend', badge);
        }
        badge.innerHTML = `<span>中 ${clampWeight(item.cjkWeight, 400)}</span><span>英 ${clampWeight(item.latinWeight, 400)}</span><span>数 ${clampWeight(item.digitWeight, 400)}</span>`;
    });
}
function scheduleRender() {
    if (renderScheduled) return;
    renderScheduled = true;
    requestAnimationFrame(async () => {
        renderScheduled = false;
        if (!document.getElementById('presetCjk')) return;
        const token = ++renderToken;
        Object.entries(SLOT_CONFIG).forEach(([slot, config]) => {
            const select = document.getElementById(config.selectId);
            if (select && !select.dataset.weightBound) {
                select.dataset.weightBound = '1';
                select.addEventListener('change', () => {
                    updateStoredSelection({ [slot]: select.value || '' });
                    renderSlotControl(slot, ++renderToken);
                });
            }
        });
        await Promise.all(Object.keys(SLOT_CONFIG).map(slot => renderSlotControl(slot, token)));
        renderPresetWeightBadges();
    });
}
function persistPresetWeights(nameHint, snapshot) {
    const presets = readPresets();
    if (!presets.length) return;
    let item = presets.find(preset => preset.name === nameHint);
    if (!item) item = presets[0];
    item.cjkWeight = clampWeight(snapshot.cjkWeight, 400);
    item.latinWeight = clampWeight(snapshot.latinWeight, 400);
    item.digitWeight = clampWeight(snapshot.digitWeight, 400);
    writePresets(presets);
    scheduleRender();
}
function bindDelegatedEvents() {
    document.addEventListener('click', event => {
        const save = event.target?.closest?.('#savePresetBtn');
        if (save) {
            const snapshot = currentSelectionFromDom();
            const inputName = (document.getElementById('presetName')?.value || '').trim();
            const fallbackName = `${fontById(snapshot.cjk)?.name || snapshot.cjk || '字体'}组合`;
            setTimeout(() => persistPresetWeights(inputName || fallbackName, snapshot), 0);
            return;
        }
        const load = event.target?.closest?.('[data-preset-load]');
        if (load) {
            const item = readPresets()[Number(load.dataset.presetLoad)];
            if (item) {
                writeState({
                    cjk: item.cjk, latin: item.latin, digit: item.digit,
                    cjkWeight: item.cjkWeight, latinWeight: item.latinWeight, digitWeight: item.digitWeight,
                });
                setTimeout(scheduleRender, 0);
            }
        }
    }, true);
}
function installStyles() {
    if (document.getElementById('workbenchWeightStyles')) return;
    const link = document.createElement('link');
    link.id = 'workbenchWeightStyles'; link.rel = 'stylesheet'; link.href = './workbench_weight_extension.css?v=14202';
    document.head.appendChild(link);
}
function initialize() {
    installStyles();
    bindDelegatedEvents();
    const observer = new MutationObserver(scheduleRender);
    observer.observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener('luoshu-mix-selection-change', scheduleRender);
    scheduleRender();
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
