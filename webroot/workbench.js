// 洛书 v14.2 Alpha1 — 字体工作台
// 纯前端实验层：复用 v14 完整复合引擎，不改动底层挂载与事务切换。

const PRESET_KEY = 'luoshu_v142_mix_presets';
const WORKBENCH_TAB_KEY = 'luoshu_v142_workbench_tab';

const state = {
    tab: localStorage.getItem(WORKBENCH_TAB_KEY) || 'preset',
    axisFont: '',
    compareA: '',
    compareB: '',
    healthFont: '',
    axisValues: {},
};

function app() { return window.App; }
function api() { return window.LuoShuV14; }
function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function usableFonts() {
    return (app()?.fonts || []).filter(item => item && item.id !== 'default' && item.valid !== false);
}
function fontById(id) { return usableFonts().find(item => item.id === id); }
function fontLabel(id) {
    if (!id) return '请选择';
    return fontById(id)?.name || id;
}
function fontFamily(font) {
    if (!font) return 'sans-serif';
    app()?.injectFontFace?.(font);
    return `'preview_${app()?.safeId?.(font.id) || String(font.id).replace(/[^a-zA-Z0-9]/g, '_')}', sans-serif`;
}
function optionList(selected = '', predicate = () => true) {
    const options = usableFonts().filter(predicate).map(font =>
        `<option value="${escapeHtml(font.id)}" ${font.id === selected ? 'selected' : ''}>${escapeHtml(font.name || font.id)} · ${escapeHtml(font.format || 'TTF')}</option>`
    ).join('');
    return `<option value="">请选择字体</option>${options}`;
}
function loadPresets() {
    try {
        const value = JSON.parse(localStorage.getItem(PRESET_KEY) || '[]');
        return Array.isArray(value) ? value.filter(item => item && item.name) : [];
    } catch (_) { return []; }
}
function savePresets(items) {
    localStorage.setItem(PRESET_KEY, JSON.stringify(items.slice(0, 20)));
}
function ensureStylesheet() {
    if (document.getElementById('workbenchStyles')) return;
    const link = document.createElement('link');
    link.id = 'workbenchStyles';
    link.rel = 'stylesheet';
    link.href = './workbench.css?v=14201';
    document.head.appendChild(link);
}
function ensureDockButton() {
    if (document.getElementById('workbenchNavBtn')) return;
    const more = document.getElementById('moreNavBtn');
    if (!more) return;
    const button = document.createElement('button');
    button.className = 'nav-btn';
    button.id = 'workbenchNavBtn';
    button.dataset.nav = 'workbench';
    button.setAttribute('aria-label', '打开字体工作台');
    button.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 5h16M7 5v14m10-14v14M4 19h16"/><path d="M9.5 9h5M9.5 12h5M9.5 15h5"/></svg><span>工作台</span>`;
    more.insertAdjacentElement('beforebegin', button);
    button.addEventListener('click', openWorkbench);
    document.documentElement.classList.add('workbench-ready');
}
function ensureModal() {
    let modal = document.getElementById('fontWorkbenchModal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.className = 'modal workbench-modal';
    modal.id = 'fontWorkbenchModal';
    modal.innerHTML = `
        <div class="workbench-sheet" role="dialog" aria-modal="true" aria-label="字体工作台">
            <header class="workbench-hero">
                <div class="workbench-emblem" aria-hidden="true"><span>中</span><i>Aa</i><b>123</b></div>
                <div class="workbench-heading"><small>LUOSHU LAB</small><h2>字体工作台</h2><p>组合预设、可变轴、字体对比与健康分析</p></div>
                <span class="workbench-version">v14.2 Alpha1</span>
                <button class="workbench-close" id="closeWorkbenchBtn" type="button" aria-label="关闭">×</button>
            </header>
            <nav class="workbench-tabs" aria-label="工作台功能">
                <button type="button" data-workbench-tab="preset"><span>组合</span><small>预设</small></button>
                <button type="button" data-workbench-tab="axis"><span>可变</span><small>轴预览</small></button>
                <button type="button" data-workbench-tab="compare"><span>对比</span><small>实验室</small></button>
                <button type="button" data-workbench-tab="health"><span>健康</span><small>评分</small></button>
            </nav>
            <main class="workbench-body" id="workbenchBody"></main>
        </div>`;
    document.body.appendChild(modal);
    modal.addEventListener('click', event => { if (event.target === modal) closeWorkbench(); });
    modal.querySelector('#closeWorkbenchBtn')?.addEventListener('click', closeWorkbench);
    modal.querySelectorAll('[data-workbench-tab]').forEach(button => button.addEventListener('click', () => switchTab(button.dataset.workbenchTab)));
    return modal;
}
async function waitForFonts() {
    if (usableFonts().length) return;
    try { await app()?.loadData?.({ background: true }); } catch (_) { /* 首页会显示真实错误 */ }
    for (let i = 0; i < 20 && !usableFonts().length; i += 1) await new Promise(resolve => setTimeout(resolve, 80));
}
async function openWorkbench() {
    const modal = ensureModal();
    document.getElementById('helpModal')?.classList.remove('show');
    if (app()?.showSearch) app().toggleSearch();
    modal.classList.add('show');
    document.body.classList.add('workbench-open');
    app()?.setDockActive?.('workbench');
    renderLoading('正在读取字体库…');
    await waitForFonts();
    normalizeSelections();
    renderTab();
}
function closeWorkbench() {
    document.getElementById('fontWorkbenchModal')?.classList.remove('show');
    document.body.classList.remove('workbench-open');
    app()?.updateDockFromScroll?.();
}
function switchTab(tab) {
    if (!['preset', 'axis', 'compare', 'health'].includes(tab)) return;
    state.tab = tab;
    localStorage.setItem(WORKBENCH_TAB_KEY, tab);
    renderTab();
}
function renderLoading(message) {
    const body = document.getElementById('workbenchBody');
    if (body) body.innerHTML = `<div class="workbench-loading"><i></i><strong>${escapeHtml(message)}</strong></div>`;
}
function normalizeSelections() {
    const fonts = usableFonts();
    const first = fonts[0]?.id || '';
    const second = fonts[1]?.id || first;
    const variable = fonts.find(item => item.variable)?.id || '';
    if (!fontById(state.axisFont)?.variable) state.axisFont = variable;
    if (!fontById(state.compareA)) state.compareA = first;
    if (!fontById(state.compareB)) state.compareB = second;
    if (!fontById(state.healthFont)) state.healthFont = first;
}
function activateTabButton() {
    document.querySelectorAll('[data-workbench-tab]').forEach(button => button.classList.toggle('active', button.dataset.workbenchTab === state.tab));
}
function renderTab() {
    activateTabButton();
    if (!usableFonts().length) {
        const body = document.getElementById('workbenchBody');
        if (body) body.innerHTML = `<div class="workbench-empty"><strong>字体库为空</strong><p>先把 TTF / OTF / TTC 放入 /sdcard/LuoShu/fonts/，刷新首页后再进入工作台。</p></div>`;
        return;
    }
    if (state.tab === 'axis') return renderAxisLab();
    if (state.tab === 'compare') return renderCompareLab();
    if (state.tab === 'health') return renderHealthLab();
    renderPresetLab();
}

function renderPresetLab() {
    const body = document.getElementById('workbenchBody');
    const mix = api()?.getMixState?.() || {};
    const presets = loadPresets();
    body.innerHTML = `
        <section class="workbench-section preset-builder">
            <div class="workbench-section-head"><div><small>COMPOSITE PRESET</small><h3>字体组合预设</h3></div><span>调用完整复合引擎</span></div>
            <div class="preset-slots">
                <label><span class="slot-mark cjk">中</span><b>中文基底</b><select id="presetCjk">${optionList(mix.cjk)}</select></label>
                <label><span class="slot-mark latin">Aa</span><b>英文字形</b><select id="presetLatin">${optionList(mix.latin)}</select></label>
                <label><span class="slot-mark digit">123</span><b>数字字形</b><select id="presetDigit">${optionList(mix.digit)}</select></label>
            </div>
            <div class="preset-name-row"><input id="presetName" type="text" maxlength="24" placeholder="预设名称，例如：阅读 / 圆润 / 极简"><button id="savePresetBtn" type="button">保存预设</button></div>
            <div class="workbench-actions"><button id="syncPresetBtn" type="button">同步到首页</button><button id="applyPresetBtn" class="primary" type="button">生成并应用</button></div>
            <p class="workbench-note">中文字体始终作为完整基底；英文与数字只替换对应字形。生成仍走 v14 的事务、进度与回滚链路。</p>
        </section>
        <section class="workbench-section">
            <div class="workbench-section-head"><div><small>SAVED</small><h3>已保存预设</h3></div><span>${presets.length} 个</span></div>
            <div class="preset-list" id="presetList">${renderPresetCards(presets)}</div>
        </section>`;
    const selection = () => ({
        cjk: document.getElementById('presetCjk')?.value || '',
        latin: document.getElementById('presetLatin')?.value || '',
        digit: document.getElementById('presetDigit')?.value || '',
    });
    document.getElementById('savePresetBtn')?.addEventListener('click', () => {
        const value = selection();
        if (!value.cjk || !value.latin || !value.digit) return app()?.showToast?.('请先选择中文、英文和数字字体');
        const name = (document.getElementById('presetName')?.value || '').trim() || `${fontLabel(value.cjk)}组合`;
        const list = loadPresets().filter(item => item.name !== name);
        list.unshift({ name, ...value, updatedAt: Date.now() });
        savePresets(list);
        app()?.showToast?.(`已保存预设：${name}`);
        renderPresetLab();
    });
    document.getElementById('syncPresetBtn')?.addEventListener('click', () => {
        const value = selection();
        if (!api()?.setMixSelection?.(value)) return app()?.showToast?.('字体组合接口尚未就绪');
        app()?.showToast?.('已同步到首页字体组合');
    });
    document.getElementById('applyPresetBtn')?.addEventListener('click', async () => {
        const value = selection();
        if (!value.cjk || !value.latin || !value.digit) return app()?.showToast?.('请先选择中文、英文和数字字体');
        api()?.setMixSelection?.(value);
        closeWorkbench();
        await api()?.applyMix?.();
    });
    body.querySelectorAll('[data-preset-load]').forEach(button => button.addEventListener('click', () => {
        const item = loadPresets()[Number(button.dataset.presetLoad)];
        if (!item) return;
        ['Cjk', 'Latin', 'Digit'].forEach(slot => {
            const key = slot.toLowerCase();
            const el = document.getElementById(`preset${slot}`);
            if (el) el.value = item[key] || '';
        });
        const input = document.getElementById('presetName');
        if (input) input.value = item.name;
        app()?.showToast?.(`已载入：${item.name}`);
    }));
    body.querySelectorAll('[data-preset-apply]').forEach(button => button.addEventListener('click', async () => {
        const item = loadPresets()[Number(button.dataset.presetApply)];
        if (!item) return;
        api()?.setMixSelection?.(item);
        closeWorkbench();
        await api()?.applyMix?.();
    }));
    body.querySelectorAll('[data-preset-delete]').forEach(button => button.addEventListener('click', () => {
        const index = Number(button.dataset.presetDelete);
        const list = loadPresets();
        const removed = list.splice(index, 1)[0];
        savePresets(list);
        app()?.showToast?.(removed ? `已删除：${removed.name}` : '预设已删除');
        renderPresetLab();
    }));
}
function renderPresetCards(presets) {
    if (!presets.length) return '<div class="workbench-empty compact"><strong>还没有预设</strong><p>在上方选择三种字体并保存。</p></div>';
    return presets.map((item, index) => `
        <article class="preset-card">
            <div class="preset-card-title"><strong>${escapeHtml(item.name)}</strong><small>${new Date(item.updatedAt || Date.now()).toLocaleDateString()}</small></div>
            <div class="preset-card-slots"><span><b>中</b>${escapeHtml(fontLabel(item.cjk))}</span><span><b>Aa</b>${escapeHtml(fontLabel(item.latin))}</span><span><b>123</b>${escapeHtml(fontLabel(item.digit))}</span></div>
            <div class="preset-card-actions"><button data-preset-load="${index}">载入</button><button data-preset-delete="${index}">删除</button><button class="primary" data-preset-apply="${index}">应用</button></div>
        </article>`).join('');
}

async function renderAxisLab() {
    const body = document.getElementById('workbenchBody');
    const variables = usableFonts().filter(item => item.variable);
    if (!variables.length) {
        body.innerHTML = '<div class="workbench-empty"><strong>没有检测到可变字体</strong><p>导入包含 fvar 表的可变 TTF / OTF 后即可调节全部轴。</p></div>';
        return;
    }
    if (!variables.some(item => item.id === state.axisFont)) state.axisFont = variables[0].id;
    body.innerHTML = `
        <section class="workbench-section">
            <div class="workbench-section-head"><div><small>VARIABLE FONT</small><h3>可变字体轴滑块</h3></div><span>实时预览</span></div>
            <label class="workbench-select"><span>字体</span><select id="axisFontSelect">${optionList(state.axisFont, item => item.variable)}</select></label>
            <div id="axisLabContent"><div class="workbench-loading"><i></i><strong>正在解析可变轴…</strong></div></div>
        </section>`;
    document.getElementById('axisFontSelect')?.addEventListener('change', event => { state.axisFont = event.target.value; state.axisValues = {}; renderAxisLab(); });
    const font = fontById(state.axisFont);
    try {
        const result = await app().analyzeFont(font);
        if (state.axisFont !== font.id || state.tab !== 'axis') return;
        renderAxisControls(font, result.variable?.axes || []);
    } catch (error) {
        const content = document.getElementById('axisLabContent');
        if (content) content.innerHTML = `<div class="workbench-empty compact"><strong>轴读取失败</strong><p>${escapeHtml(error?.message || String(error))}</p></div>`;
    }
}
function renderAxisControls(font, axes) {
    const content = document.getElementById('axisLabContent');
    if (!content) return;
    if (!axes.length) {
        content.innerHTML = '<div class="workbench-empty compact"><strong>未发现可调轴</strong><p>字体被标记为可变字体，但分析器没有读取到 fvar 轴。</p></div>';
        return;
    }
    const family = fontFamily(font);
    state.axisValues = Object.fromEntries(axes.map(axis => [String(axis.tag).trim(), Number(state.axisValues[String(axis.tag).trim()] ?? axis.default)]));
    content.innerHTML = `
        <div class="axis-preview" id="axisPreview" style="font-family:${family}"><strong id="axisPreviewMain">洛书字体工作台</strong><span id="axisPreviewSub">Variable Font · 中文 English 0123456789</span><input id="axisPreviewInput" value="天地玄黄 · Hello LuoShu 2026" aria-label="可变字体预览文字"></div>
        <div class="axis-controls">${axes.map(axis => {
            const tag = String(axis.tag || '').trim();
            const value = state.axisValues[tag];
            const step = Math.max(0.01, (Number(axis.max) - Number(axis.min)) / 200);
            return `<label class="axis-control"><span><b>${escapeHtml(tag)}</b><small>${escapeHtml(axisName(tag))}</small><output id="axisValue_${escapeHtml(tag)}">${formatAxisValue(value)}</output></span><input type="range" data-axis-tag="${escapeHtml(tag)}" min="${Number(axis.min)}" max="${Number(axis.max)}" step="${step}" value="${value}"><i><em>${formatAxisValue(axis.min)}</em><em>默认 ${formatAxisValue(axis.default)}</em><em>${formatAxisValue(axis.max)}</em></i></label>`;
        }).join('')}</div>
        <div class="workbench-actions"><button id="resetAxesBtn" type="button">恢复默认轴</button><button id="copyAxesBtn" class="primary" type="button">复制轴参数</button></div>
        <p class="workbench-note">Alpha1 先提供完整轴的实时预览与参数导出；真正写入复合字体将在后续版本接入生成引擎。</p>`;
    const sync = () => {
        const settings = Object.entries(state.axisValues).map(([tag, value]) => `"${tag}" ${Number(value)}`).join(', ');
        ['axisPreview', 'axisPreviewMain', 'axisPreviewSub', 'axisPreviewInput'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.style.fontVariationSettings = settings;
        });
    };
    content.querySelectorAll('[data-axis-tag]').forEach(slider => slider.addEventListener('input', event => {
        const tag = event.target.dataset.axisTag;
        state.axisValues[tag] = Number(event.target.value);
        const output = document.getElementById(`axisValue_${tag}`);
        if (output) output.textContent = formatAxisValue(state.axisValues[tag]);
        sync();
    }));
    document.getElementById('axisPreviewInput')?.addEventListener('input', event => {
        const value = event.target.value || ' ';
        const main = document.getElementById('axisPreviewMain');
        const sub = document.getElementById('axisPreviewSub');
        if (main) main.textContent = value;
        if (sub) sub.textContent = value;
    });
    document.getElementById('resetAxesBtn')?.addEventListener('click', () => {
        state.axisValues = Object.fromEntries(axes.map(axis => [String(axis.tag).trim(), Number(axis.default)]));
        renderAxisControls(font, axes);
    });
    document.getElementById('copyAxesBtn')?.addEventListener('click', () => {
        const text = Object.entries(state.axisValues).map(([tag, value]) => `${tag}=${formatAxisValue(value)}`).join(', ');
        app()?.copyText?.(text, '可变轴参数已复制');
    });
    sync();
}
function axisName(tag) {
    return ({ wght: '字重', wdth: '字宽', slnt: '倾斜', ital: '意大利体', opsz: '光学尺寸', GRAD: '等级', XTRA: '横向扩展', YTAS: '上升部' })[tag] || '自定义轴';
}
function formatAxisValue(value) {
    const number = Number(value);
    return Number.isInteger(number) ? String(number) : number.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
}

function renderCompareLab() {
    const body = document.getElementById('workbenchBody');
    const fontA = fontById(state.compareA) || usableFonts()[0];
    const fontB = fontById(state.compareB) || usableFonts()[1] || fontA;
    state.compareA = fontA?.id || '';
    state.compareB = fontB?.id || '';
    body.innerHTML = `
        <section class="workbench-section compare-lab">
            <div class="workbench-section-head"><div><small>A / B TEST</small><h3>字体对比实验室</h3></div><span>同文同尺寸</span></div>
            <div class="compare-toolbar"><label><span>字体 A</span><select id="compareA">${optionList(state.compareA)}</select></label><label><span>字体 B</span><select id="compareB">${optionList(state.compareB)}</select></label></div>
            <div class="compare-inputs"><input id="compareText" value="洛书字体对比 · Hello 0123456789" aria-label="对比文字"><label><span>字号</span><input id="compareSize" type="range" min="18" max="64" value="34"><output id="compareSizeValue">34px</output></label></div>
            <div class="compare-grid">
                <article><header><b>A</b><span>${escapeHtml(fontA?.name || fontA?.id || '')}</span></header><div id="comparePreviewA" style="font-family:${fontFamily(fontA)}">洛书字体对比 · Hello 0123456789</div><small>${escapeHtml(fontA?.format || '')} · ${escapeHtml(fontA?.size || '')} · ${fontA?.variable ? '可变字体' : `${(fontA?.weights || []).length || 1} 档字重`}</small></article>
                <article><header><b>B</b><span>${escapeHtml(fontB?.name || fontB?.id || '')}</span></header><div id="comparePreviewB" style="font-family:${fontFamily(fontB)}">洛书字体对比 · Hello 0123456789</div><small>${escapeHtml(fontB?.format || '')} · ${escapeHtml(fontB?.size || '')} · ${fontB?.variable ? '可变字体' : `${(fontB?.weights || []).length || 1} 档字重`}</small></article>
            </div>
            <p class="workbench-note">两边使用完全相同的文字、字号和行高，便于比较字面率、数字风格、标点位置与中英文协调性。</p>
        </section>`;
    document.getElementById('compareA')?.addEventListener('change', event => { state.compareA = event.target.value; renderCompareLab(); });
    document.getElementById('compareB')?.addEventListener('change', event => { state.compareB = event.target.value; renderCompareLab(); });
    const sync = () => {
        const text = document.getElementById('compareText')?.value || ' ';
        const size = Number(document.getElementById('compareSize')?.value || 34);
        ['comparePreviewA', 'comparePreviewB'].forEach(id => {
            const el = document.getElementById(id);
            if (el) { el.textContent = text; el.style.fontSize = `${size}px`; }
        });
        const out = document.getElementById('compareSizeValue');
        if (out) out.textContent = `${size}px`;
    };
    document.getElementById('compareText')?.addEventListener('input', sync);
    document.getElementById('compareSize')?.addEventListener('input', sync);
    sync();
}

async function renderHealthLab() {
    const body = document.getElementById('workbenchBody');
    const font = fontById(state.healthFont) || usableFonts()[0];
    state.healthFont = font?.id || '';
    body.innerHTML = `
        <section class="workbench-section">
            <div class="workbench-section-head"><div><small>FONT HEALTH</small><h3>字体健康评分</h3></div><span>真实 cmap 抽样</span></div>
            <label class="workbench-select"><span>分析字体</span><select id="healthFontSelect">${optionList(state.healthFont)}</select></label>
            <div id="healthContent"><div class="workbench-loading"><i></i><strong>正在分析字体结构与覆盖范围…</strong></div></div>
        </section>`;
    document.getElementById('healthFontSelect')?.addEventListener('change', event => { state.healthFont = event.target.value; renderHealthLab(); });
    try {
        const result = await app().analyzeFont(font);
        if (state.healthFont !== font.id || state.tab !== 'health') return;
        renderHealthResult(font, result);
    } catch (error) {
        const content = document.getElementById('healthContent');
        if (content) content.innerHTML = `<div class="workbench-empty compact"><strong>分析失败</strong><p>${escapeHtml(error?.message || String(error))}</p></div>`;
    }
}
function heatRow(label, item) {
    const percent = Math.max(0, Math.min(100, Number(item?.percent || 0)));
    const active = Math.round(percent / 10);
    return `<div class="health-heat-row"><span>${escapeHtml(label)}</span><div>${Array.from({ length: 10 }, (_, index) => `<i class="${index < active ? 'active' : ''}"></i>`).join('')}</div><b>${percent}%</b></div>`;
}
function renderHealthResult(font, result) {
    const content = document.getElementById('healthContent');
    if (!content) return;
    const score = Number(result.assessment?.score || 0);
    const level = result.assessment?.level || 'warn';
    const coverage = result.coverage || {};
    const axes = result.variable?.axes || [];
    const warnings = result.assessment?.warnings || [];
    content.innerHTML = `
        <div class="health-summary">
            <div class="health-score ${escapeHtml(level)}"><strong>${score}</strong><span>健康分</span></div>
            <div><small>${escapeHtml(result.assessment?.label || '字体分析')}</small><h4>${escapeHtml(font.name || font.id)}</h4><p>${warnings.length ? `${warnings.length} 项需要注意` : '未发现明显结构风险'}</p></div>
        </div>
        <div class="health-source-grid">
            <span><small>来源</small><b>本地字体库</b><em>${escapeHtml(font.file || '')}</em></span>
            <span><small>格式</small><b>${escapeHtml(font.format || '未知')}</b><em>${escapeHtml(font.size || '')}</em></span>
            <span><small>字重结构</small><b>${font.variable ? `可变 · ${axes.length} 轴` : `${(font.weights || []).length || 1} 档静态字重`}</b><em>${escapeHtml((font.weights || []).join(' / '))}</em></span>
        </div>
        <div class="health-heatmap"><div class="health-heat-title"><strong>字符覆盖热力图</strong><small>每格约代表 10%</small></div>
            ${heatRow('常用中文', coverage.cjk)}${heatRow('英文字母', coverage.latin)}${heatRow('数字', coverage.digits)}${heatRow('标点', coverage.punctuation)}${heatRow('特殊符号', coverage.symbols)}${heatRow('日文假名', coverage.kana)}${heatRow('韩文', coverage.hangul)}
        </div>
        ${warnings.length ? `<div class="health-warnings">${warnings.map(item => `<span>! ${escapeHtml(item)}</span>`).join('')}</div>` : '<div class="health-ok">✓ 当前抽样范围内未发现明显问题</div>'}
        <div class="workbench-actions"><button id="copyHealthReportBtn" class="primary" type="button">复制健康报告</button></div>`;
    document.getElementById('copyHealthReportBtn')?.addEventListener('click', () => {
        const lines = [`字体：${font.name || font.id}`, `健康分：${score}`, `格式：${font.format || '未知'}`, `大小：${font.size || '未知'}`, `可变轴：${axes.map(axis => `${axis.tag} ${axis.min}-${axis.max}`).join('；') || '无'}`, `警告：${warnings.join('；') || '无'}`];
        app()?.copyText?.(lines.join('\n'), '健康报告已复制');
    });
}

function initWorkbench() {
    ensureStylesheet();
    ensureDockButton();
    ensureModal();
    window.LuoShuWorkbench = { open: openWorkbench, close: closeWorkbench, render: renderTab };
}

document.addEventListener('DOMContentLoaded', initWorkbench);
