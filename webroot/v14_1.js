// 洛书 v14.1：首次引导、设备能力、APatch 持久化提示与旧 UI 清理。
import { exec } from './kernelsu.js';

const MODULE_DIR = '/data/adb/modules/LuoShu';
const CAPABILITY = `${MODULE_DIR}/common/device_capabilities.sh`;
const GUIDE_KEY = 'luoshu_v141_onboarding_done';
let capabilityData = null;
let capabilityLoading = false;
let capabilityAppliedToMix = false;

function escapeHtml(value) {
    return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
function parseJson(output) {
    const line = String(output || '').split('\n').find(item => item.trim().startsWith('{'));
    return line ? JSON.parse(line.trim()) : null;
}
async function shell(command) {
    const result = await exec(command);
    if (Number(result?.errno || 0) !== 0) throw new Error(String(result?.stderr || '命令执行失败'));
    return String(result?.stdout || result?.stderr || '');
}
function removeLegacyUi() {
    ['emojiSection', 'moreImportZipBtn', 'moreOpenFolderBtn', 'moreOpenEmojiFolderBtn', 'generateReportBtn', 'copyFontPathBtn', 'stabilityRescueButton', 'stabilityModal', 'openStabilityBtn'].forEach(id => document.getElementById(id)?.remove());
    document.querySelectorAll('[data-module-version]').forEach(node => { node.textContent = 'v14.1'; });
    const engine = document.getElementById('engineVersion');
    if (engine) engine.textContent = 'v14.1';
    try {
        Object.keys(localStorage).filter(key => /emoji/i.test(key) && key.startsWith('luoshu')).forEach(key => localStorage.removeItem(key));
    } catch (_) { /* ignore */ }
}
function guideModal() {
    if (document.getElementById('v141Guide')) return;
    let done = false;
    try { done = localStorage.getItem(GUIDE_KEY) === '1'; } catch (_) { /* ignore */ }
    if (done) return;
    const modal = document.createElement('div');
    modal.id = 'v141Guide';
    modal.className = 'v141-guide show';
    modal.innerHTML = `
      <div class="v141-guide-sheet" role="dialog" aria-modal="true">
        <div class="v141-guide-mark">洛</div>
        <div class="v141-guide-copy">
          <span>首次使用</span><h2>先关闭“默认卸载模块”</h2>
          <p>请在 Root 管理器设置中关闭 <b>默认卸载模块</b>，否则重启后洛书可能被自动移除。</p>
        </div>
        <div class="v141-guide-steps">
          <div><b>1</b><span><strong>关闭默认卸载模块</strong><small>Magisk / KernelSU / SukiSU Ultra / APatch 均需检查</small></span></div>
          <div><b>2</b><span><strong>字体放入 /sdcard/LuoShu/fonts/</strong><small>支持真实 TTF、OTF、TTC</small></span></div>
          <div><b>3</b><span><strong>推荐 Mountify</strong><small>不要同时启用其他字体覆盖模块</small></span></div>
        </div>
        <button id="v141GuideDone" type="button">我已关闭，进入洛书</button>
      </div>`;
    document.body.appendChild(modal);
    document.body.classList.add('v141-guide-open');
    modal.querySelector('#v141GuideDone')?.addEventListener('click', () => {
        try { localStorage.setItem(GUIDE_KEY, '1'); } catch (_) { /* ignore */ }
        modal.classList.remove('show');
        document.body.classList.remove('v141-guide-open');
        setTimeout(() => modal.remove(), 260);
    });
}
function applyDigitCapability(data) {
    const digitSlot = document.querySelector('[data-mix-slot="digit"]');
    if (!digitSlot || data.digitIndependent) return;
    digitSlot.setAttribute('aria-disabled', 'true');
    const em = digitSlot.querySelector('em');
    if (em) em.textContent = '此设备没有稳定的独立数字入口，将跟随英文字体';
    capabilityAppliedToMix = true;
}
function renderCapability(data) {
    let card = document.getElementById('v141Capability');
    if (!card) {
        const anchor = document.getElementById('fontMixPanel') || document.getElementById('listSection');
        if (!anchor) return false;
        card = document.createElement('section');
        card.id = 'v141Capability';
        card.className = 'v141-capability';
        anchor.insertAdjacentElement('beforebegin', card);
    }
    const digit = data.digitIndependent ? '独立映射' : '跟随英文';
    const persistClass = data.persistent ? 'ok' : 'bad';
    card.innerHTML = `
      <div class="v141-cap-head"><div><span>设备能力</span><h2>${escapeHtml(data.romName || 'Android')}</h2></div><b class="${persistClass}">${escapeHtml(data.root || 'Root')}</b></div>
      <div class="v141-cap-grid">
        <div><small>中文</small><strong>独立映射</strong></div>
        <div><small>英文</small><strong>独立映射</strong></div>
        <div><small>数字</small><strong>${digit}</strong></div>
        <div><small>挂载</small><strong>${escapeHtml(data.mount || '原生')}</strong></div>
      </div>
      <p class="v141-persist ${persistClass}">${data.persistent ? '模块持久化状态正常' : escapeHtml(data.persistentMessage || '模块持久化异常')}</p>`;
    document.documentElement.classList.toggle('digit-follows-latin', !data.digitIndependent);
    applyDigitCapability(data);
    return true;
}
async function loadCapability() {
    if (capabilityData) {
        renderCapability(capabilityData);
        return;
    }
    if (capabilityLoading) return;
    capabilityLoading = true;
    try {
        const result = parseJson(await shell(`sh '${CAPABILITY}'`));
        if (result?.status === 'ok' && result.data) {
            capabilityData = result.data;
            renderCapability(capabilityData);
        }
    } catch (error) {
        console.warn('[洛书] 设备能力读取失败', error);
    } finally {
        capabilityLoading = false;
    }
}
function start() {
    removeLegacyUi();
    guideModal();
    loadCapability();
    const observer = new MutationObserver(() => {
        removeLegacyUi();
        if (capabilityData && !document.getElementById('v141Capability')) renderCapability(capabilityData);
        if (capabilityData && !capabilityAppliedToMix) applyDigitCapability(capabilityData);
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 8000);
}
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
else start();
