// 洛书 v14.2 RC2 - Root / Mountify 环境识别与 UI 精修
import { exec } from './kernelsu.js';
import './mix_state_guard.js?v=14210';
import './workbench_bridge.js?v=14210';
import './workbench.js?v=14210';

const UI_VERSION = '14210';

function installRefinedStyle() {
    if (document.querySelector('link[data-luoshu-refine]')) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = `ui_refine.css?v=${UI_VERSION}`;
    link.dataset.luoshuRefine = 'true';
    document.head.appendChild(link);
}

function cleanLegacyHelp() {
    const help = document.getElementById('helpModal');
    if (!help) return;

    help.querySelectorAll('.help-note').forEach(item => {
        if (/Hybrid Mount|Magic Mount|Ignore/i.test(item.textContent || '')) item.remove();
    });
    help.querySelector('.more-advanced')?.remove();

    // RC2 只允许完整重启完成字体切换。保留节点以兼容旧事件绑定，但不再展示热重启入口。
    const restartUi = help.querySelector('#restartUIBtn');
    if (restartUi) {
        restartUi.hidden = true;
        restartUi.style.display = 'none';
        restartUi.setAttribute('aria-hidden', 'true');
        restartUi.tabIndex = -1;
    }

    const title = help.querySelector('.more-title-row h2');
    if (title) title.textContent = '设置';
    const subtitle = help.querySelector('.more-heading > p');
    if (subtitle) subtitle.textContent = '外观、文件与运行环境';
}

function createEnvironmentCard() {
    const helpBody = document.querySelector('#helpModal .help-body');
    if (!helpBody || document.getElementById('runtimeEnvironmentCard')) return null;

    const card = document.createElement('section');
    card.id = 'runtimeEnvironmentCard';
    card.className = 'runtime-card';
    card.innerHTML = `
        <div class="runtime-card-head">
            <span class="runtime-card-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M4 7h16v10H4z"/><path d="M8 17v3m8-3v3M8 4v3m8-3v3"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/></svg>
            </span>
            <span><strong>运行环境</strong><small>自动识别 Root 管理器与模块挂载环境</small></span>
            <span class="runtime-state-dot" id="runtimeStateDot" aria-hidden="true"></span>
        </div>
        <div class="runtime-values">
            <div class="runtime-value">
                <span class="runtime-value-mark root" aria-hidden="true">R</span>
                <span><small>Root 管理器</small><b id="runtimeRootName">检测中…</b></span>
            </div>
            <div class="runtime-value">
                <span class="runtime-value-mark mount" aria-hidden="true">M</span>
                <span><small>挂载环境</small><b id="runtimeMountName">检测中…</b></span>
            </div>
        </div>
        <div class="runtime-support">已适配 Magisk · KernelSU · SukiSU Ultra · APatch</div>`;

    const compat = helpBody.querySelector('.compat-row');
    if (compat) compat.insertAdjacentElement('afterend', card);
    else helpBody.prepend(card);

    const note = document.createElement('div');
    note.id = 'mountifyRecommendation';
    note.className = 'help-note mountify-note';
    note.innerHTML = '<span class="note-icon">M</span><span><strong>Mountify · 推荐元模块</strong><small id="mountifyRecommendationText">正在检测 Mountify 状态…</small></span>';
    const googleNote = helpBody.querySelector('.help-note');
    if (googleNote) googleNote.insertAdjacentElement('afterend', note);
    else helpBody.appendChild(note);
    return card;
}

async function detectEnvironment() {
    const rootEl = document.getElementById('runtimeRootName');
    const mountEl = document.getElementById('runtimeMountName');
    const dotEl = document.getElementById('runtimeStateDot');
    const mountifyText = document.getElementById('mountifyRecommendationText');
    const mountifyNote = document.getElementById('mountifyRecommendation');
    if (!rootEl || !mountEl) return;

    const command = `
ROOT_NAME="已授权 Root"
if command -v apd >/dev/null 2>&1 || [ -d /data/adb/ap ] || [ -d /data/adb/apatch ]; then
  ROOT_NAME="APatch"
elif command -v ksud >/dev/null 2>&1 || [ -d /data/adb/ksu ]; then
  KSU_INFO="$(ksud -V 2>/dev/null || ksud --version 2>/dev/null || true)"
  case "$KSU_INFO $(getprop ro.build.version.incremental 2>/dev/null)" in
    *SukiSU*|*sukisu*|*SUKISU*) ROOT_NAME="SukiSU Ultra" ;;
    *) ROOT_NAME="KernelSU" ;;
  esac
elif command -v magisk >/dev/null 2>&1 || [ -d /data/adb/magisk ]; then
  ROOT_NAME="Magisk"
fi
MOUNT_NAME="原生模块挂载"
MOUNTIFY_STATE="0"
if [ -d /data/adb/modules/mountify ] && [ ! -f /data/adb/modules/mountify/disable ] && [ ! -f /data/adb/modules/mountify/remove ]; then
  MOUNT_NAME="Mountify"
  MOUNTIFY_STATE="1"
elif [ -d /data/adb/mountify ]; then
  MOUNT_NAME="Mountify"
  MOUNTIFY_STATE="1"
fi
printf '%s|%s|%s\n' "$ROOT_NAME" "$MOUNT_NAME" "$MOUNTIFY_STATE"
`;

    try {
        const result = await exec(command);
        const raw = `${result?.stdout || ''}\n${result?.stderr || ''}`.trim();
        const output = raw.split('\n').map(line => line.trim()).filter(Boolean).reverse().find(line => line.split('|').length >= 3) || '';
        const [rootName, mountName, mountifyState] = output.split('|');
        rootEl.textContent = rootName || '已授权 Root';
        mountEl.textContent = mountName || '原生模块挂载';
        if (dotEl) dotEl.classList.add('ready');
        const mountifyEnabled = mountifyState === '1';
        if (mountifyText) mountifyText.textContent = mountifyEnabled ? '已检测到 Mountify，当前为推荐且已启用的元模块环境。' : '需要元模块时，推荐使用 Mountify；当前使用原生模块挂载。';
        mountifyNote?.classList.toggle('is-active', mountifyEnabled);
        document.documentElement.dataset.rootManager = (rootName || 'root').toLowerCase().replace(/\s+/g, '-');
        document.documentElement.dataset.mountEngine = mountifyEnabled ? 'mountify' : 'native';
    } catch (error) {
        console.warn('[洛书] 环境识别失败', error);
        rootEl.textContent = '已授权 Root';
        mountEl.textContent = '原生模块挂载';
        if (dotEl) dotEl.classList.add('warning');
        if (mountifyText) mountifyText.textContent = '环境检测暂不可用；需要元模块时推荐使用 Mountify。';
    }
}

function initialize() {
    installRefinedStyle();
    cleanLegacyHelp();
    createEnvironmentCard();
    detectEnvironment();
    document.body.classList.add('luoshu-refined');
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
else initialize();
