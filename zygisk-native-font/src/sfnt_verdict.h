// LuoShu native font: icon/symbol font verdict over raw sfnt bytes.
//
// Zero-copy: parses directly in the caller's buffer, never allocates, never writes to it.
// Every failure (truncated tables, unknown formats, WOFF/WOFF2, byte budget exceeded) ends in
// KEEP, i.e. "leave the app's own font alone".
#pragma once

#include <cstddef>
#include <cstdint>

namespace lsnf {

enum class Verdict : uint8_t {
    Keep = 0,          // leave the font untouched
    ReplaceLatin = 1,  // body text font with Latin coverage
    ReplaceCjk = 2,    // body text font with CJK coverage (LuoShu Hans face also covers Latin)
};

enum class Reason : uint8_t {
    ParseError = 0,
    TooSmall,
    Woff,
    Budget,
    NameToken,
    ColorTable,
    SymbolCmap,
    NoCmap,
    PrivateUse,
    DigitsOnly,
    NotText,
    Monospace,
    BodyLatin,
    BodyCjk,
};

struct CmapStats {
    uint32_t latin = 0;    // A-Z a-z mapped (0..52)
    uint32_t digits = 0;   // 0-9 mapped (0..10)
    uint32_t cjk = 0;      // U+4E00-9FFF and U+3400-4DBF mapped
    uint32_t pua = 0;      // U+E000-F8FF, planes 15/16 mapped
};

struct VerdictResult {
    Verdict verdict = Verdict::Keep;
    Reason reason = Reason::ParseError;
    CmapStats stats;
    uint32_t touched_bytes = 0;
};

// Upper bound of bytes the parser may read from one font before giving up (KEEP).
constexpr uint32_t kTouchBudget = 256u * 1024u;

// Pure classification, no cache. nameHint may be null (file path or asset name).
VerdictResult classify(const uint8_t *data, size_t size, uint32_t ttcIndex, const char *nameHint);

// Same as classify() with a process-local cache keyed by the font's table directory.
// Thread safe; the cache holds at most kCacheSlots entries and is never persisted.
constexpr size_t kCacheSlots = 512;
VerdictResult classifyCached(const uint8_t *data, size_t size, uint32_t ttcIndex, const char *nameHint,
                             bool *cacheHit = nullptr);
void clearVerdictCache();

// True when the lower-cased name contains one of the generated keep tokens.
bool nameHasKeepToken(const char *name, size_t len);

const char *verdictName(Verdict v);
const char *reasonName(Reason r);

}  // namespace lsnf
