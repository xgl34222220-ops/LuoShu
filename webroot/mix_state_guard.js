// 洛书 v14.2 Alpha3：保护组合字体的多轴状态不被旧版三字段保存逻辑覆盖。
const KEY = 'luoshu_v14_mix_selection';
const SLOTS = ['cjk', 'latin', 'digit'];
const originalSetItem = Storage.prototype.setItem;
let insideGuard = false;

function parse(value) {
    try { const result = JSON.parse(String(value || 'null')); return result && typeof result === 'object' ? result : {}; }
    catch (_) { return {}; }
}

Storage.prototype.setItem = function guardedSetItem(key, rawValue) {
    if (insideGuard || this !== localStorage || key !== KEY) return originalSetItem.call(this, key, rawValue);
    const current = parse(this.getItem(KEY));
    const incoming = parse(rawValue);
    const merged = { ...current, ...incoming };
    let fontChangedAny = false;
    SLOTS.forEach(slot => {
        const axesKey = `${slot}Axes`;
        const weightKey = `${slot}Weight`;
        const fontChanged = Object.prototype.hasOwnProperty.call(incoming, slot) && String(incoming[slot] || '') !== String(current[slot] || '');
        if (fontChanged && !Object.prototype.hasOwnProperty.call(incoming, axesKey)) {
            fontChangedAny = true;
            merged[axesKey] = {};
            delete merged[weightKey];
        } else {
            if (!Object.prototype.hasOwnProperty.call(incoming, axesKey) && Object.prototype.hasOwnProperty.call(current, axesKey)) merged[axesKey] = current[axesKey];
            if (!Object.prototype.hasOwnProperty.call(incoming, weightKey) && Object.prototype.hasOwnProperty.call(current, weightKey)) merged[weightKey] = current[weightKey];
        }
    });
    insideGuard = true;
    try { return originalSetItem.call(this, key, JSON.stringify(merged)); }
    finally {
        insideGuard = false;
        if (fontChangedAny) queueMicrotask(() => window.dispatchEvent(new CustomEvent('luoshu-mix-storage-change', { detail: merged })));
    }
};
