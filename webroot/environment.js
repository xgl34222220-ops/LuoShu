// 洛书 v13.5 Stable Hotfix2 - 环境识别与界面精简
import { exec } from './kernelsu.js';

const UI_VERSION = '13502';

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
        if (item.textContent.includes('Hybrid Mount')) item.remove();
    });
    help.querySelector('.more-advanced')?.remove();

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
        </div>
        <div class="runtime-values">
            <div><small>Root 管理器</small><b id="runtimeRootName">检测中…</b></div>
            <div><small>挂载环境</small><b id="runtimeMountName">检测中…</b></div>
        </div>
        <div class="runtime-support">Magisk · KernelSU · SukiSU Ultra · APatch</div>`;

    const compat = helpBody.querySelector('.compat-row');
    if (compat) compat.insertAdjacentElement('afterend', card);
    else helpBody.prepend(card);

    const note = document.createElement('div');
    note.className = 'help-note mountify-note';
    note.innerHTML = '<span class="note-icon">M</span><span><strong>Mountify</strong><small>已适配 Mountify。其他元模块不在当前稳定支持范围内，界面不再提供相关引导。</small></span>';
    const googleNote = helpBody.querySelector('.help-note');
    if (googleNote) googleNote.insertAdjacentElement('afterend', note);
    else helpBody.appendChild(note);
    return card;
}

async function detectEnvironment() {
    const rootEl = document.getElementById('runtimeRootName');
    const mountEl = document.getElementById('runtimeMountName');
    if (!rootEl || !mountEl) return;

    const command = [
        'ROOT_NAME="Root"',
        'if [ -d /data/adb/ap ] || [ -d /data/adb/apatch ] || command -v apd >/dev/null 2>&1; then ROOT_NAME="APatch";',
        'elif [ -d /data/adb/ksu ]; then',
        '  if grep -Rqi "sukisu" /data/adb/ksu 2>/dev/null; then ROOT_NAME="SukiSU Ultra"; else ROOT_NAME="KernelSU"; fi;',
        'elif [ -d /data/adb/magisk ] || command -v magisk >/dev/null 2>&1; then ROOT_NAME="Magisk"; fi',
        'MOUNT_NAME="原生模块挂载"',
        '[ -d /data/adb/mountify ] && MOUNT_NAME="Mountify"',
        'printf "%s|%s\\n" "$ROOT_NAME" "$MOUNT_NAME"'
    ].join(' ');

    try {
        const result = await exec(command);
        const output = String(result?.stdout || result?.stderr || '').trim().split('\n').pop() || '';
        const [rootName, mountName] = output.split('|');
        rootEl.textContent = rootName || 'Root';
        mountEl.textContent = mountName || '原生模块挂载';
        document.documentElement.dataset.rootManager = (rootName || 'root').toLowerCase().replace(/\s+/g, '-');
        document.documentElement.dataset.mountEngine = mountName === 'Mountify' ? 'mountify' : 'native';
    } catch (_) {
        rootEl.textContent = '已授权 Root';
        mountEl.textContent = '原生模块挂载';
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
