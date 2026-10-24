// LuoShu native font: icon/symbol font verdict over raw sfnt bytes.
// Written from the OpenType specification (sfnt directory, name, cmap formats 0/4/6/12/13,
// post, OS/2 panose). See sfnt_verdict.h for the contract.
#include "sfnt_verdict.h"

#include <atomic>
#include <cstring>

namespace lsnf {
namespace {

constexpr uint32_t tag(char a, char b, char c, char d) {
    return (uint32_t(uint8_t(a)) << 24) | (uint32_t(uint8_t(b)) << 16) | (uint32_t(uint8_t(c)) << 8) |
           uint32_t(uint8_t(d));
}

constexpr uint32_t kTagTtcf = tag('t', 't', 'c', 'f');
constexpr uint32_t kTagWoff = tag('w', 'O', 'F', 'F');
constexpr uint32_t kTagWoff2 = tag('w', 'O', 'F', '2');
constexpr uint32_t kTagOtto = tag('O', 'T', 'T', 'O');
constexpr uint32_t kTagTrue = tag('t', 'r', 'u', 'e');
constexpr uint32_t kTagTyp1 = tag('t', 'y', 'p', '1');
constexpr uint32_t kPuaIconMin = 256;

const char *const kKeepWords[] = {
#define LSNF_KEEP_WORD(s) s,
#include "keep_words.inc"
#undef LSNF_KEEP_WORD
};

// Bounds- and budget-checked reader over the caller's buffer.
struct Reader {
    const uint8_t *d;
    size_t n;
    uint32_t touched = 0;
    bool over = false;

    bool take(size_t off, size_t len) {
        if (off > n || len > n - off) return false;
        if (len > kTouchBudget || touched + len > kTouchBudget) {
            over = true;
            return false;
        }
        touched += uint32_t(len);
        return true;
    }
    bool inside(size_t off, size_t len) const { return off <= n && len <= n - off; }
    uint16_t u16(size_t off) const { return uint16_t((d[off] << 8) | d[off + 1]); }
    uint32_t u32(size_t off) const {
        return (uint32_t(d[off]) << 24) | (uint32_t(d[off + 1]) << 16) | (uint32_t(d[off + 2]) << 8) |
               uint32_t(d[off + 3]);
    }
};

struct Table {
    uint32_t off = 0;
    uint32_t len = 0;
    bool present = false;
};

struct Directory {
    size_t dirOff = 0;  // offset of the sfnt offset table inside the buffer
    uint16_t numTables = 0;
    Table cmap, name, post, os2, head, maxp;
    bool color = false;
};

struct Span {
    uint32_t lo, hi;
    uint8_t bucket;  // 0 latin, 1 digits, 2 cjk, 3 pua
};

constexpr Span kSpans[] = {
    {0x30, 0x39, 1},       {0x41, 0x5A, 0},       {0x61, 0x7A, 0},       {0x3400, 0x4DBF, 2},
    {0x4E00, 0x9FFF, 2},   {0xE000, 0xF8FF, 3},   {0xF0000, 0xFFFFD, 3}, {0x100000, 0x10FFFD, 3},
};

void addBucket(CmapStats &s, uint8_t bucket, uint32_t count) {
    switch (bucket) {
        case 0: s.latin += count; break;
        case 1: s.digits += count; break;
        case 2: s.cjk += count; break;
        default: s.pua += count; break;
    }
}

void clampStats(CmapStats &s) {
    if (s.latin > 52) s.latin = 52;
    if (s.digits > 10) s.digits = 10;
}

char lowerAscii(uint32_t c) {
    if (c >= 'A' && c <= 'Z') return char(c - 'A' + 'a');
    if (c >= 0x20 && c < 0x7F) return char(c);
    return ' ';
}

bool containsToken(const char *lower, size_t len) {
    for (const char *w : kKeepWords) {
        size_t wl = strlen(w);
        if (wl == 0 || wl > len) continue;
        for (size_t i = 0; i + wl <= len; ++i) {
            if (memcmp(lower + i, w, wl) == 0) return true;
        }
    }
    return false;
}

enum class DirStatus { Ok, TooSmall, Woff, Bad };

DirStatus readDirectory(Reader &r, uint32_t ttcIndex, Directory &dir) {
    if (r.n < 12) return DirStatus::TooSmall;
    if (!r.take(0, 12)) return DirStatus::Bad;
    uint32_t first = r.u32(0);
    if (first == kTagWoff || first == kTagWoff2) return DirStatus::Woff;
    size_t off = 0;
    if (first == kTagTtcf) {
        uint32_t numFonts = r.u32(8);
        if (ttcIndex >= numFonts || !r.take(12 + size_t(ttcIndex) * 4, 4)) return DirStatus::Bad;
        off = r.u32(12 + size_t(ttcIndex) * 4);
        if (!r.take(off, 12)) return DirStatus::Bad;
    } else if (ttcIndex != 0) {
        return DirStatus::Bad;
    }
    uint32_t version = r.u32(off);
    if (version != 0x00010000u && version != kTagOtto && version != kTagTrue && version != kTagTyp1) {
        return DirStatus::Bad;
    }
    dir.dirOff = off;
    dir.numTables = r.u16(off + 4);
    if (dir.numTables == 0 || !r.take(off + 12, size_t(dir.numTables) * 16)) return DirStatus::Bad;
    for (uint16_t i = 0; i < dir.numTables; ++i) {
        size_t rec = off + 12 + size_t(i) * 16;
        uint32_t t = r.u32(rec);
        Table tb;
        tb.off = r.u32(rec + 8);
        tb.len = r.u32(rec + 12);
        tb.present = r.inside(tb.off, tb.len);
        if (!tb.present) continue;
        switch (t) {
            case tag('c', 'm', 'a', 'p'): dir.cmap = tb; break;
            case tag('n', 'a', 'm', 'e'): dir.name = tb; break;
            case tag('p', 'o', 's', 't'): dir.post = tb; break;
            case tag('O', 'S', '/', '2'): dir.os2 = tb; break;
            case tag('h', 'e', 'a', 'd'): dir.head = tb; break;
            case tag('m', 'a', 'x', 'p'): dir.maxp = tb; break;
            case tag('C', 'O', 'L', 'R'):
            case tag('C', 'B', 'D', 'T'):
            case tag('s', 'b', 'i', 'x'):
            case tag('S', 'V', 'G', ' '): dir.color = true; break;
            default: break;
        }
    }
    return DirStatus::Ok;
}

bool nameTableHasKeepToken(Reader &r, const Table &t) {
    if (!t.present || t.len < 6 || !r.take(t.off, 6)) return false;
    uint16_t count = r.u16(t.off + 2);
    uint32_t strOff = t.off + r.u16(t.off + 4);
    if (count > 512) count = 512;
    if (!r.take(t.off + 6, size_t(count) * 12)) return false;
    char buf[160];
    for (uint16_t i = 0; i < count; ++i) {
        size_t rec = t.off + 6 + size_t(i) * 12;
        uint16_t platform = r.u16(rec), nameId = r.u16(rec + 6);
        uint16_t len = r.u16(rec + 8), off = r.u16(rec + 10);
        if (!(nameId == 1 || nameId == 2 || nameId == 4 || nameId == 6 || nameId == 16)) continue;
        if (len == 0 || len > 256 || !r.take(size_t(strOff) + off, len)) continue;
        const uint8_t *s = r.d + strOff + off;
        size_t bl = 0;
        if (platform == 0 || platform == 3) {
            for (size_t k = 0; k + 1 < len && bl < sizeof(buf); k += 2) {
                uint32_t c = (uint32_t(s[k]) << 8) | s[k + 1];
                buf[bl++] = lowerAscii(c);
            }
        } else if (platform == 1) {
            for (size_t k = 0; k < len && bl < sizeof(buf); ++k) buf[bl++] = lowerAscii(s[k]);
        } else {
            continue;
        }
        if (containsToken(buf, bl)) return true;
    }
    return false;
}

enum class CmapStatus { Ok, Unsupported, Bad };

CmapStatus countFormat4(Reader &r, size_t base, CmapStats &st) {
    if (!r.take(base, 14)) return CmapStatus::Bad;
    uint16_t segX2 = r.u16(base + 6);
    if (segX2 == 0 || (segX2 & 1)) return CmapStatus::Bad;
    size_t endA = base + 14, startA = endA + segX2 + 2, deltaA = startA + segX2, roA = deltaA + segX2;
    if (!r.take(endA, size_t(segX2) * 4 + 2)) return CmapStatus::Bad;
    uint16_t segs = segX2 / 2;
    for (uint16_t i = 0; i < segs; ++i) {
        uint32_t end = r.u16(endA + 2 * i), start = r.u16(startA + 2 * i);
        uint16_t delta = r.u16(deltaA + 2 * i), ro = r.u16(roA + 2 * i);
        if (start > end || start == 0xFFFF) continue;
        for (const Span &sp : kSpans) {
            if (sp.lo > 0xFFFF) continue;
            uint32_t lo = start > sp.lo ? start : sp.lo, hi = end < sp.hi ? end : sp.hi;
            if (lo > hi) continue;
            uint32_t count = 0;
            if (ro == 0) {
                count = hi - lo + 1;
                uint32_t zeroC = uint32_t(0x10000u - delta) & 0xFFFFu;
                if (zeroC >= lo && zeroC <= hi) --count;
            } else {
                size_t roPos = roA + 2 * size_t(i);
                for (uint32_t c = lo; c <= hi; ++c) {
                    size_t g = roPos + ro + 2 * size_t(c - start);
                    if (!r.take(g, 2)) return CmapStatus::Bad;
                    if (r.u16(g) != 0) ++count;
                }
            }
            addBucket(st, sp.bucket, count);
        }
    }
    return CmapStatus::Ok;
}

CmapStatus countFormat12or13(Reader &r, size_t base, bool constant, CmapStats &st) {
    if (!r.take(base, 16)) return CmapStatus::Bad;
    uint32_t n = r.u32(base + 12);
    size_t groups = base + 16;
    if (!r.inside(groups, size_t(n) * 12)) return CmapStatus::Bad;
    for (const Span &sp : kSpans) {
        // Groups are sorted by start code (spec requirement): binary search the first group
        // whose end >= sp.lo, then walk forward while start <= sp.hi. Only touched groups count.
        uint32_t lo = 0, hi = n;
        while (lo < hi) {
            uint32_t mid = lo + (hi - lo) / 2;
            size_t g = groups + size_t(mid) * 12;
            if (!r.take(g + 4, 4)) return CmapStatus::Bad;
            if (r.u32(g + 4) < sp.lo) lo = mid + 1; else hi = mid;
        }
        for (uint32_t i = lo; i < n; ++i) {
            size_t g = groups + size_t(i) * 12;
            if (!r.take(g, 12)) return CmapStatus::Bad;
            uint32_t s = r.u32(g), e = r.u32(g + 4), gid = r.u32(g + 8);
            if (s > sp.hi) break;
            if (s > e) return CmapStatus::Bad;
            uint32_t a = s > sp.lo ? s : sp.lo, b = e < sp.hi ? e : sp.hi;
            if (a > b) continue;
            uint32_t count = b - a + 1;
            if (constant) {
                if (gid == 0) count = 0;
            } else if (gid == 0 && a == s) {
                --count;
            }
            addBucket(st, sp.bucket, count);
        }
    }
    return CmapStatus::Ok;
}

CmapStatus countFormat6(Reader &r, size_t base, CmapStats &st) {
    if (!r.take(base, 10)) return CmapStatus::Bad;
    uint32_t first = r.u16(base + 6), count = r.u16(base + 8);
    if (count == 0) return CmapStatus::Ok;
    uint32_t last = first + count - 1;
    for (const Span &sp : kSpans) {
        uint32_t a = first > sp.lo ? first : sp.lo, b = last < sp.hi ? last : sp.hi;
        if (a > b) continue;
        uint32_t mapped = 0;
        for (uint32_t c = a; c <= b; ++c) {
            size_t g = base + 10 + 2 * size_t(c - first);
            if (!r.take(g, 2)) return CmapStatus::Bad;
            if (r.u16(g) != 0) ++mapped;
        }
        addBucket(st, sp.bucket, mapped);
    }
    return CmapStatus::Ok;
}

CmapStatus countFormat0(Reader &r, size_t base, CmapStats &st) {
    if (!r.take(base, 6 + 256)) return CmapStatus::Bad;
    for (const Span &sp : kSpans) {
        if (sp.lo > 0xFF) continue;
        uint32_t mapped = 0;
        for (uint32_t c = sp.lo; c <= sp.hi && c <= 0xFF; ++c) {
            if (r.d[base + 6 + c] != 0) ++mapped;
        }
        addBucket(st, sp.bucket, mapped);
    }
    return CmapStatus::Ok;
}

CmapStatus countSubtable(Reader &r, size_t base, CmapStats &st) {
    if (!r.take(base, 2)) return CmapStatus::Bad;
    switch (r.u16(base)) {
        case 0: return countFormat0(r, base, st);
        case 4: return countFormat4(r, base, st);
        case 6: return countFormat6(r, base, st);
        case 12: return countFormat12or13(r, base, false, st);
        case 13: return countFormat12or13(r, base, true, st);
        default: return CmapStatus::Unsupported;
    }
}

int encodingRank(uint16_t platform, uint16_t encoding) {
    if (platform == 3 && encoding == 10) return 0;
    if (platform == 0 && (encoding == 4 || encoding == 6)) return 1;
    if (platform == 3 && encoding == 1) return 2;
    if (platform == 0 && encoding == 3) return 3;
    if (platform == 0 && encoding <= 2) return 4;
    return -1;
}

enum class CmapResult { Counted, SymbolOnly, Missing, Bad };

CmapResult readCmap(Reader &r, const Table &t, CmapStats &st) {
    if (!t.present || t.len < 4 || !r.take(t.off, 4)) return CmapResult::Missing;
    uint16_t num = r.u16(t.off + 2);
    if (num > 64) num = 64;
    if (!r.take(t.off + 4, size_t(num) * 8)) return CmapResult::Bad;
    bool symbol = false;
    for (int rank = 0; rank <= 4; ++rank) {
        for (uint16_t i = 0; i < num; ++i) {
            size_t rec = t.off + 4 + size_t(i) * 8;
            uint16_t p = r.u16(rec), e = r.u16(rec + 2);
            if (p == 3 && e == 0) symbol = true;
            if (encodingRank(p, e) != rank) continue;
            uint32_t sub = r.u32(rec + 4);
            if (sub >= t.len) continue;
            CmapStats tmp;
            CmapStatus s = countSubtable(r, size_t(t.off) + sub, tmp);
            if (s == CmapStatus::Ok) {
                clampStats(tmp);
                st = tmp;
                return CmapResult::Counted;
            }
            if (s == CmapStatus::Bad) return CmapResult::Bad;
        }
    }
    return symbol ? CmapResult::SymbolOnly : CmapResult::Missing;
}

bool isMonospace(Reader &r, const Directory &dir) {
    if (dir.post.present && dir.post.len >= 16 && r.take(dir.post.off + 12, 4) && r.u32(dir.post.off + 12) != 0) {
        return true;
    }
    if (dir.os2.present && dir.os2.len >= 42 && r.take(dir.os2.off + 32, 10)) {
        uint8_t familyType = r.d[dir.os2.off + 32], proportion = r.d[dir.os2.off + 35];
        if (familyType == 2 && proportion == 9) return true;
    }
    return false;
}

VerdictResult finish(VerdictResult res, const Reader &r) {
    res.touched_bytes = r.touched;
    return res;
}

const char *basenameOf(const char *path, size_t *len) {
    const char *base = path;
    for (const char *p = path; *p; ++p) {
        if (*p == '/') base = p + 1;
    }
    *len = strlen(base);
    return base;
}

bool hintHasKeepToken(const char *hint) {
    if (!hint || !*hint) return false;
    size_t len = 0;
    const char *base = basenameOf(hint, &len);
    return nameHasKeepToken(base, len);
}

}  // namespace

bool nameHasKeepToken(const char *name, size_t len) {
    char buf[256];
    if (len > sizeof(buf)) len = sizeof(buf);
    for (size_t i = 0; i < len; ++i) buf[i] = lowerAscii(uint8_t(name[i]));
    return containsToken(buf, len);
}

VerdictResult classify(const uint8_t *data, size_t size, uint32_t ttcIndex, const char *nameHint) {
    VerdictResult res;
    if (!data || size < 12) {
        res.reason = Reason::TooSmall;
        return res;
    }
    Reader r{data, size};
    if (hintHasKeepToken(nameHint)) {
        res.reason = Reason::NameToken;
        return res;
    }
    Directory dir;
    switch (readDirectory(r, ttcIndex, dir)) {
        case DirStatus::Ok: break;
        case DirStatus::TooSmall: res.reason = Reason::TooSmall; return finish(res, r);
        case DirStatus::Woff: res.reason = Reason::Woff; return finish(res, r);
        case DirStatus::Bad: res.reason = r.over ? Reason::Budget : Reason::ParseError; return finish(res, r);
    }
    if (nameTableHasKeepToken(r, dir.name)) {
        res.reason = Reason::NameToken;
        return finish(res, r);
    }
    if (r.over) { res.reason = Reason::Budget; return finish(res, r); }
    if (dir.color) {
        res.reason = Reason::ColorTable;
        return finish(res, r);
    }
    switch (readCmap(r, dir.cmap, res.stats)) {
        case CmapResult::Counted: break;
        case CmapResult::SymbolOnly: res.reason = Reason::SymbolCmap; return finish(res, r);
        case CmapResult::Missing: res.reason = r.over ? Reason::Budget : Reason::NoCmap; return finish(res, r);
        case CmapResult::Bad: res.reason = r.over ? Reason::Budget : Reason::ParseError; return finish(res, r);
    }
    const CmapStats &s = res.stats;
    uint64_t total = uint64_t(s.latin) + s.cjk + s.pua;
    // Icon fonts carry hundreds of PUA glyphs (ligature icon fonts also map a-z). Real text faces
    // such as DejaVu Sans ship a few dozen PUA ligatures/variants, so a small PUA count never counts.
    if ((s.pua >= kPuaIconMin && uint64_t(s.pua) * 10 >= total * 3) ||
        (s.pua > 0 && s.latin < 40 && s.pua > s.latin + s.cjk)) {
        res.reason = Reason::PrivateUse;
        return finish(res, r);
    }
    if (s.latin < 10 && s.digits == 10) {
        res.reason = Reason::DigitsOnly;
        return finish(res, r);
    }
    if (s.latin < 40 && s.cjk < 1000) {
        res.reason = Reason::NotText;
        return finish(res, r);
    }
    if (isMonospace(r, dir)) {
        res.reason = Reason::Monospace;
        return finish(res, r);
    }
    if (r.over) { res.reason = Reason::Budget; return finish(res, r); }
    if (s.cjk >= 1000) {
        res.verdict = Verdict::ReplaceCjk;
        res.reason = Reason::BodyCjk;
    } else {
        res.verdict = Verdict::ReplaceLatin;
        res.reason = Reason::BodyLatin;
    }
    return finish(res, r);
}

// ---- process-local cache -------------------------------------------------------------

namespace {

struct Slot {
    uint64_t key;
    VerdictResult res;
    bool used;
};

Slot g_slots[kCacheSlots];
std::atomic_flag g_lock = ATOMIC_FLAG_INIT;

struct SpinGuard {
    SpinGuard() { while (g_lock.test_and_set(std::memory_order_acquire)) {} }
    ~SpinGuard() { g_lock.clear(std::memory_order_release); }
};

uint64_t mix(uint64_t h, uint64_t v) {
    h ^= v + 0x9E3779B97F4A7C15ull + (h << 6) + (h >> 2);
    return h;
}

uint64_t fmix(uint64_t k) {
    k ^= k >> 33;
    k *= 0xFF51AFD7ED558CCDull;
    k ^= k >> 33;
    k *= 0xC4CEB9FE1A85EC53ull;
    k ^= k >> 33;
    return k;
}

// Key: size, ttc index, raw table directory, head.checkSumAdjustment, maxp.numGlyphs.
bool cacheKey(const uint8_t *data, size_t size, uint32_t ttcIndex, uint64_t *out) {
    Reader r{data, size};
    Directory dir;
    if (readDirectory(r, ttcIndex, dir) != DirStatus::Ok) return false;
    uint64_t h = fmix(uint64_t(size) ^ (uint64_t(ttcIndex) << 48));
    const uint8_t *p = data + dir.dirOff;
    size_t len = 12 + size_t(dir.numTables) * 16;
    uint64_t fnv = 0xCBF29CE484222325ull;
    for (size_t i = 0; i < len; ++i) {
        fnv ^= p[i];
        fnv *= 0x100000001B3ull;
    }
    h = mix(h, fnv);
    if (dir.head.present && dir.head.len >= 12) h = mix(h, r.u32(dir.head.off + 8));
    if (dir.maxp.present && dir.maxp.len >= 6) h = mix(h, r.u16(dir.maxp.off + 4));
    *out = fmix(h) | 1;  // never zero
    return true;
}

}  // namespace

VerdictResult classifyCached(const uint8_t *data, size_t size, uint32_t ttcIndex, const char *nameHint,
                             bool *cacheHit) {
    if (cacheHit) *cacheHit = false;
    if (hintHasKeepToken(nameHint)) {
        VerdictResult res;
        res.reason = Reason::NameToken;
        return res;
    }
    uint64_t key = 0;
    if (!data || !cacheKey(data, size, ttcIndex, &key)) return classify(data, size, ttcIndex, nullptr);
    size_t home = size_t(key % kCacheSlots);
    {
        SpinGuard g;
        for (size_t i = 0; i < 8; ++i) {
            const Slot &s = g_slots[(home + i) % kCacheSlots];
            if (!s.used) break;
            if (s.key == key) {
                if (cacheHit) *cacheHit = true;
                return s.res;
            }
        }
    }
    VerdictResult res = classify(data, size, ttcIndex, nullptr);
    SpinGuard g;
    size_t target = home;
    for (size_t i = 0; i < 8; ++i) {
        size_t idx = (home + i) % kCacheSlots;
        if (!g_slots[idx].used || g_slots[idx].key == key) {
            target = idx;
            break;
        }
    }
    g_slots[target] = Slot{key, res, true};
    return res;
}

void clearVerdictCache() {
    SpinGuard g;
    for (Slot &s : g_slots) s.used = false;
}

const char *verdictName(Verdict v) {
    switch (v) {
        case Verdict::Keep: return "keep";
        case Verdict::ReplaceLatin: return "replace_latin";
        case Verdict::ReplaceCjk: return "replace_cjk";
    }
    return "keep";
}

const char *reasonName(Reason r) {
    switch (r) {
        case Reason::ParseError: return "parse_error";
        case Reason::TooSmall: return "too_small";
        case Reason::Woff: return "woff";
        case Reason::Budget: return "budget";
        case Reason::NameToken: return "name_token";
        case Reason::ColorTable: return "color_table";
        case Reason::SymbolCmap: return "symbol_cmap";
        case Reason::NoCmap: return "no_cmap";
        case Reason::PrivateUse: return "private_use";
        case Reason::DigitsOnly: return "digits_only";
        case Reason::NotText: return "not_text";
        case Reason::Monospace: return "monospace";
        case Reason::BodyLatin: return "body_latin";
        case Reason::BodyCjk: return "body_cjk";
    }
    return "unknown";
}

}  // namespace lsnf
