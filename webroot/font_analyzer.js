// LuoShu v13.3 Beta2 - lightweight SFNT/OTF cmap and variable-axis analyzer
// Runs entirely in WebUI. It samples real cmap mappings and never modifies a font file.

const SAMPLE_SETS = {
    latin: Array.from('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz').map(ch => ch.codePointAt(0)),
    digits: Array.from('0123456789').map(ch => ch.codePointAt(0)),
    cjk: Array.from('的一是不了人我在有他这为之大来以个中上们到说国和地也子时道出而要于就下得可你年生自会那后能对着事其里所去行过家十用发天如然作方成者多日都三小军二无同么经法当起与好看学进种将还分此心前面又定见只主没公从').map(ch => ch.codePointAt(0)),
    punctuation: Array.from('，。！？；：“”‘’（）【】《》、…—·,.!?;:\"\'()[]{}').map(ch => ch.codePointAt(0)),
    symbols: [0x00A5,0x20AC,0x00A3,0x00A9,0x00AE,0x2122,0x2190,0x2191,0x2192,0x2193,0x21D2,0x221A,0x221E,0x2260,0x2264,0x2265,0x25A0,0x25A1,0x25B2,0x25BC,0x2605,0x2606,0x2713,0x2715,0x271A,0x2764],
    kana: Array.from('あいうえおかきくけこアイウエオカキクケコ').map(ch => ch.codePointAt(0)),
    hangul: Array.from('가나다라마바사아자차카타파하').map(ch => ch.codePointAt(0)),
    emoji: [0x1F600,0x1F602,0x1F60D,0x1F618,0x1F622,0x1F44D,0x1F44F,0x1F64F,0x1F389,0x1F525,0x1F680,0x1F4A1,0x1F4F1,0x1F496,0x1F31F,0x1F308,0x1F431,0x1F436,0x1F34E,0x1F37A],
    pua: Array.from({ length: 72 }, (_, i) => 0xE000 + i * 0x58)
};

function readTag(view, offset) {
    return String.fromCharCode(
        view.getUint8(offset), view.getUint8(offset + 1),
        view.getUint8(offset + 2), view.getUint8(offset + 3)
    );
}

function findTable(view, baseOffset, tag) {
    const numTables = view.getUint16(baseOffset + 4, false);
    const tableStart = baseOffset + 12;
    for (let i = 0; i < numTables; i++) {
        const rec = tableStart + i * 16;
        if (rec + 16 > view.byteLength) break;
        if (readTag(view, rec) === tag) {
            const offset = view.getUint32(rec + 8, false);
            const length = view.getUint32(rec + 12, false);
            if (offset + length <= view.byteLength) return { offset, length };
        }
    }
    return null;
}

function getSfntBase(view) {
    const signature = readTag(view, 0);
    if (signature === 'ttcf') {
        const numFonts = view.getUint32(8, false);
        if (numFonts < 1 || view.byteLength < 16) throw new Error('TTC 字体集合为空');
        return view.getUint32(12, false);
    }
    return 0;
}

function parseFormat12(view, offset) {
    const nGroups = view.getUint32(offset + 12, false);
    const groups = [];
    let pos = offset + 16;
    const maxGroups = Math.min(nGroups, 200000);
    for (let i = 0; i < maxGroups; i++, pos += 12) {
        if (pos + 12 > view.byteLength) break;
        groups.push({
            start: view.getUint32(pos, false),
            end: view.getUint32(pos + 4, false),
            glyph: view.getUint32(pos + 8, false)
        });
    }
    return {
        format: 12,
        has(cp) {
            let lo = 0, hi = groups.length - 1;
            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                const g = groups[mid];
                if (cp < g.start) hi = mid - 1;
                else if (cp > g.end) lo = mid + 1;
                else return (g.glyph + cp - g.start) !== 0;
            }
            return false;
        }
    };
}

function parseFormat4(view, offset) {
    const length = view.getUint16(offset + 2, false);
    const end = Math.min(offset + length, view.byteLength);
    const segCount = view.getUint16(offset + 6, false) >> 1;
    const endCodesOffset = offset + 14;
    const startCodesOffset = endCodesOffset + segCount * 2 + 2;
    const idDeltaOffset = startCodesOffset + segCount * 2;
    const idRangeOffsetOffset = idDeltaOffset + segCount * 2;
    if (idRangeOffsetOffset + segCount * 2 > end) throw new Error('cmap format 4 已损坏');

    const segments = [];
    for (let i = 0; i < segCount; i++) {
        segments.push({
            start: view.getUint16(startCodesOffset + i * 2, false),
            end: view.getUint16(endCodesOffset + i * 2, false),
            delta: view.getInt16(idDeltaOffset + i * 2, false),
            rangePos: idRangeOffsetOffset + i * 2,
            range: view.getUint16(idRangeOffsetOffset + i * 2, false)
        });
    }

    return {
        format: 4,
        has(cp) {
            if (cp > 0xFFFF) return false;
            let lo = 0, hi = segments.length - 1;
            while (lo <= hi) {
                const mid = (lo + hi) >> 1;
                const s = segments[mid];
                if (cp < s.start) hi = mid - 1;
                else if (cp > s.end) lo = mid + 1;
                else {
                    if (s.range === 0) return ((cp + s.delta) & 0xFFFF) !== 0;
                    const glyphPos = s.rangePos + s.range + (cp - s.start) * 2;
                    if (glyphPos + 2 > end) return false;
                    const glyph = view.getUint16(glyphPos, false);
                    return glyph !== 0 && ((glyph + s.delta) & 0xFFFF) !== 0;
                }
            }
            return false;
        }
    };
}

function parseCmap(view, baseOffset) {
    const table = findTable(view, baseOffset, 'cmap');
    if (!table) throw new Error('字体缺少 cmap 字符映射表');
    const cmap = table.offset;
    const numTables = view.getUint16(cmap + 2, false);
    const candidates = [];
    for (let i = 0; i < numTables; i++) {
        const rec = cmap + 4 + i * 8;
        if (rec + 8 > view.byteLength) break;
        const platform = view.getUint16(rec, false);
        const encoding = view.getUint16(rec + 2, false);
        const subOffset = cmap + view.getUint32(rec + 4, false);
        if (subOffset + 2 > view.byteLength) continue;
        const format = view.getUint16(subOffset, false);
        let priority = 0;
        if (format === 12) priority = platform === 3 && encoding === 10 ? 100 : platform === 0 ? 90 : 80;
        if (format === 4) priority = platform === 3 ? 70 : platform === 0 ? 60 : 50;
        if (priority) candidates.push({ format, offset: subOffset, priority });
    }
    candidates.sort((a, b) => b.priority - a.priority);
    if (!candidates.length) throw new Error('暂不支持该字体的 cmap 格式');
    const chosen = candidates[0];
    return chosen.format === 12 ? parseFormat12(view, chosen.offset) : parseFormat4(view, chosen.offset);
}

function coverage(cmap, codePoints) {
    let present = 0;
    for (const cp of codePoints) if (cmap.has(cp)) present++;
    return {
        present,
        total: codePoints.length,
        percent: Math.round((present / Math.max(codePoints.length, 1)) * 100)
    };
}

function tableFlags(view, baseOffset) {
    const tags = ['COLR', 'CPAL', 'CBDT', 'CBLC', 'sbix', 'SVG '];
    const found = {};
    for (const tag of tags) found[tag.trim()] = !!findTable(view, baseOffset, tag);
    return found;
}


function fixed16_16(value) {
    return Math.round((value / 65536) * 1000) / 1000;
}

function parseFvar(view, baseOffset) {
    const table = findTable(view, baseOffset, 'fvar');
    if (!table || table.length < 16) return { axes: [], instanceCount: 0 };
    const off = table.offset;
    const axesArrayOffset = view.getUint16(off + 4, false);
    const axisCount = view.getUint16(off + 8, false);
    const axisSize = view.getUint16(off + 10, false);
    const instanceCount = view.getUint16(off + 12, false);
    if (axisSize < 20 || axisCount > 64) return { axes: [], instanceCount };
    const axes = [];
    let pos = off + axesArrayOffset;
    for (let i = 0; i < axisCount; i++, pos += axisSize) {
        if (pos + 20 > Math.min(off + table.length, view.byteLength)) break;
        axes.push({
            tag: readTag(view, pos),
            min: fixed16_16(view.getInt32(pos + 4, false)),
            default: fixed16_16(view.getInt32(pos + 8, false)),
            max: fixed16_16(view.getInt32(pos + 12, false)),
            flags: view.getUint16(pos + 16, false),
            nameId: view.getUint16(pos + 18, false)
        });
    }
    return { axes, instanceCount };
}

function buildAssessment(result) {
    const c = result.coverage;
    const warnings = [];
    if (c.latin.percent < 90) warnings.push('英文字母覆盖偏低');
    if (c.digits.percent < 100) warnings.push('数字字形不完整');
    if (c.cjk.percent < 70) warnings.push('常用中文抽样覆盖偏低，可能出现漏字');
    if (c.pua.percent >= 22) warnings.push('包含较多私用区字形，部分 ROM 图标可能被覆盖');
    if (c.symbols.percent < 35) warnings.push('特殊符号覆盖较少，将依赖系统回退字体');

    let level = 'excellent';
    let label = '优秀';
    if (warnings.length || c.cjk.percent < 90 || c.latin.percent < 98) {
        level = 'good'; label = '良好';
    }
    if (c.cjk.percent < 70 || c.latin.percent < 80 || c.digits.percent < 80 || c.pua.percent >= 40) {
        level = 'caution'; label = '需注意';
    }
    const score = Math.max(0, Math.min(100, Math.round(
        c.cjk.percent * 0.48 + c.latin.percent * 0.18 + c.digits.percent * 0.10 +
        c.punctuation.percent * 0.12 + c.symbols.percent * 0.07 + (100 - Math.min(c.pua.percent, 50)) * 0.05
    )));
    return { level, label, score, warnings };
}

export function analyzeFontBuffer(buffer) {
    const view = new DataView(buffer);
    if (view.byteLength < 20) throw new Error('字体文件过小或已损坏');
    const baseOffset = getSfntBase(view);
    if (baseOffset + 12 > view.byteLength) throw new Error('字体头部无效');
    const signature = readTag(view, baseOffset);
    const rawSignature = view.getUint32(baseOffset, false);
    const valid = signature === 'OTTO' || signature === 'true' || signature === 'typ1' || rawSignature === 0x00010000;
    if (!valid) throw new Error('不是有效的 TTF / OTF 字体');
    const cmap = parseCmap(view, baseOffset);
    const variable = parseFvar(view, baseOffset);
    const result = {
        signature: signature === '\u0000\u0001\u0000\u0000' ? 'TTF' : signature === 'OTTO' ? 'OTF' : signature,
        cmapFormat: cmap.format,
        colorTables: tableFlags(view, baseOffset),
        variable,
        coverage: {}
    };
    for (const [name, points] of Object.entries(SAMPLE_SETS)) result.coverage[name] = coverage(cmap, points);
    result.hasColorEmoji = Object.values(result.colorTables).some(Boolean);
    result.assessment = buildAssessment(result);
    return result;
}

export async function analyzeFontUrl(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`读取字体失败（${response.status}）`);
    const buffer = await response.arrayBuffer();
    return analyzeFontBuffer(buffer);
}

export function formatAnalysisReport(font, result) {
    const c = result.coverage;
    const lines = [
        'LuoShu 字体检测报告',
        `字体：${font.name || font.id}`,
        `文件：${font.file || '未知'}`,
        `格式：${font.format || result.signature || '未知'}`,
        `大小：${font.size || '未知'}`,
        '',
        `综合评分：${result.assessment.score}/100（${result.assessment.label}）`,
        `中文抽样：${c.cjk.percent}%`,
        `英文：${c.latin.percent}%`,
        `数字：${c.digits.percent}%`,
        `标点：${c.punctuation.percent}%`,
        `符号：${c.symbols.percent}%`,
        `日文假名：${c.kana.percent}%`,
        `韩文：${c.hangul.percent}%`,
        `Emoji 字形：${c.emoji.percent}%${result.hasColorEmoji ? '（检测到彩色表）' : ''}`,
        `私用区抽样：${c.pua.percent}%`,
        `可变字体：${result.variable?.axes?.length ? '是' : '否'}`,
        ...(result.variable?.axes?.length ? [`可变轴：${result.variable.axes.map(a => `${a.tag} ${a.min}–${a.max}（默认 ${a.default}）`).join('；')}`, `命名实例：${result.variable.instanceCount || 0}`] : []),
        '',
        result.assessment.warnings.length ? `提示：${result.assessment.warnings.join('；')}` : '提示：未发现明显风险',
        '说明：覆盖率为抽样结果，系统仍可能通过 fallback 字体补齐缺失字符。'
    ];
    return lines.join('\n');
}
