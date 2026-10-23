#include "config.h"

#include <cstring>

namespace lsnf {
namespace {

constexpr char kMagic[4] = {'L', 'S', 'N', 'F'};

uint16_t rd16(const uint8_t *p) { return uint16_t(p[0] | (p[1] << 8)); }
uint32_t rd32(const uint8_t *p) {
    return uint32_t(p[0]) | (uint32_t(p[1]) << 8) | (uint32_t(p[2]) << 16) | (uint32_t(p[3]) << 24);
}
uint64_t rd64(const uint8_t *p) { return uint64_t(rd32(p)) | (uint64_t(rd32(p + 4)) << 32); }
void wr16(uint8_t *p, uint16_t v) {
    p[0] = uint8_t(v);
    p[1] = uint8_t(v >> 8);
}
void wr32(uint8_t *p, uint32_t v) {
    for (int i = 0; i < 4; ++i) p[i] = uint8_t(v >> (8 * i));
}
void wr64(uint8_t *p, uint64_t v) {
    wr32(p, uint32_t(v));
    wr32(p + 4, uint32_t(v >> 32));
}

int cmpBytes(const uint8_t *a, size_t al, const uint8_t *b, size_t bl) {
    size_t n = al < bl ? al : bl;
    int c = n ? memcmp(a, b, n) : 0;
    if (c != 0) return c;
    return al < bl ? -1 : (al > bl ? 1 : 0);
}

bool validName(const char *s, size_t len) {
    if (len == 0 || len > kPackageMaxLen) return false;
    for (size_t i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)s[i];
        bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' ||
                  c == '_';
        if (!ok) return false;
    }
    return true;
}

}  // namespace

uint64_t bootHash(const char *bootId, size_t len) {
    while (len > 0 && (bootId[0] == ' ' || bootId[0] == '\n' || bootId[0] == '\t' || bootId[0] == '\r')) {
        ++bootId;
        --len;
    }
    while (len > 0 && (bootId[len - 1] == ' ' || bootId[len - 1] == '\n' || bootId[len - 1] == '\t' ||
                       bootId[len - 1] == '\r')) {
        --len;
    }
    uint64_t h = 0xCBF29CE484222325ull;
    for (size_t i = 0; i < len; ++i) {
        h ^= (unsigned char)bootId[i];
        h *= 0x100000001B3ull;
    }
    return h;
}

bool parseConfig(const uint8_t *data, size_t size, ConfigView *out) {
    if (!data || !out || size < kConfigHeaderSize || size > kConfigMaxBytes) return false;
    if (memcmp(data, kMagic, 4) != 0 || rd32(data + 4) != kConfigVersion) return false;
    ConfigView v;
    v.data = data;
    v.size = size;
    v.flags = rd32(data + 8);
    v.count = rd32(data + 12);
    v.bootHash = rd64(data + 16);
    v.stringsSize = rd32(data + 24);
    size_t entryBytes = size_t(v.count) * kConfigEntrySize;
    if (v.count > (kConfigMaxBytes / kConfigEntrySize)) return false;
    if (kConfigHeaderSize + entryBytes + v.stringsSize != size) return false;
    v.entries = data + kConfigHeaderSize;
    v.strings = v.entries + entryBytes;
    const uint8_t *prev = nullptr;
    size_t prevLen = 0;
    for (uint32_t i = 0; i < v.count; ++i) {
        const uint8_t *e = v.entries + size_t(i) * kConfigEntrySize;
        uint32_t off = rd32(e);
        uint16_t len = rd16(e + 4);
        if (len == 0 || len > kPackageMaxLen || off > v.stringsSize || len > v.stringsSize - off) return false;
        const uint8_t *name = v.strings + off;
        if (prev && cmpBytes(prev, prevLen, name, len) >= 0) return false;
        prev = name;
        prevLen = len;
    }
    *out = v;
    return true;
}

uint16_t lookupPackage(const ConfigView &cfg, const char *pkg, size_t len) {
    if (!pkg || len == 0) return 0;
    uint32_t lo = 0, hi = cfg.count;
    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;
        const uint8_t *e = cfg.entries + size_t(mid) * kConfigEntrySize;
        int c = cmpBytes(cfg.strings + rd32(e), rd16(e + 4), reinterpret_cast<const uint8_t *>(pkg), len);
        if (c == 0) return rd16(e + 6);
        if (c < 0) lo = mid + 1; else hi = mid;
    }
    return 0;
}

size_t buildConfig(ConfigEntryIn *entries, size_t count, uint32_t flags, uint64_t hash, uint8_t *out,
                   size_t cap) {
    // Insertion sort: lists are small (hundreds) and this keeps the writer allocation free.
    for (size_t i = 1; i < count; ++i) {
        ConfigEntryIn key = entries[i];
        size_t j = i;
        while (j > 0 && strcmp(entries[j - 1].name, key.name) > 0) {
            entries[j] = entries[j - 1];
            --j;
        }
        entries[j] = key;
    }
    size_t unique = 0;
    for (size_t i = 0; i < count; ++i) {
        if (!validName(entries[i].name, strlen(entries[i].name))) return 0;
        if (unique > 0 && strcmp(entries[unique - 1].name, entries[i].name) == 0) {
            entries[unique - 1].bits = uint16_t(entries[unique - 1].bits | entries[i].bits);
        } else {
            entries[unique++] = entries[i];
        }
    }
    size_t strBytes = 0;
    for (size_t i = 0; i < unique; ++i) strBytes += strlen(entries[i].name);
    size_t total = kConfigHeaderSize + unique * kConfigEntrySize + strBytes;
    if (total > kConfigMaxBytes || total > cap || !out) return 0;
    memcpy(out, kMagic, 4);
    wr32(out + 4, kConfigVersion);
    wr32(out + 8, flags);
    wr32(out + 12, uint32_t(unique));
    wr64(out + 16, hash);
    wr32(out + 24, uint32_t(strBytes));
    wr32(out + 28, 0);
    uint8_t *ent = out + kConfigHeaderSize;
    uint8_t *str = ent + unique * kConfigEntrySize;
    uint32_t off = 0;
    for (size_t i = 0; i < unique; ++i) {
        size_t len = strlen(entries[i].name);
        wr32(ent + i * kConfigEntrySize, off);
        wr16(ent + i * kConfigEntrySize + 4, uint16_t(len));
        wr16(ent + i * kConfigEntrySize + 6, entries[i].bits);
        memcpy(str + off, entries[i].name, len);
        off += uint32_t(len);
    }
    return total;
}

size_t packageLength(const char *niceName) {
    if (!niceName) return 0;
    size_t n = 0;
    while (niceName[n] && niceName[n] != ':') ++n;
    return n;
}

Decision decide(const ProcessInfo &proc, const ConfigView *cfg, uint64_t currentBootHash) {
    Decision d;
    int32_t appId = proc.uid % 100000;
    if (appId < 10000) { d.skip = Skip::SystemUid; return d; }
    if (appId >= 90000) { d.skip = Skip::Isolated; return d; }
    if (proc.childZygote) { d.skip = Skip::ChildZygote; return d; }
    if (proc.onDenylist) { d.skip = Skip::Denylist; return d; }
    size_t len = packageLength(proc.niceName);
    if (len == 0) { d.skip = Skip::NoName; return d; }
    static const char *const kHard[] = {
        "com.android.systemui",
        "io.github.xgl34222220.luoshu",
        "io.github.xgl34222220.luoshu.globalfont",
    };
    for (const char *h : kHard) {
        if (strlen(h) == len && memcmp(h, proc.niceName, len) == 0) { d.skip = Skip::HardExcluded; return d; }
    }
    if (!cfg) { d.skip = Skip::NoConfig; return d; }
    d.verbose = (cfg->flags & kFlagVerbose) != 0;
    if (!(cfg->flags & kFlagEnabled)) { d.skip = Skip::Disabled; return d; }
    if (cfg->bootHash != currentBootHash) { d.skip = Skip::StaleBoot; return d; }
    d.bits = lookupPackage(*cfg, proc.niceName, len);
    if (d.bits & kPkgExclude) { d.skip = Skip::Excluded; return d; }
    d.skip = Skip::None;
    return d;
}

const char *skipName(Skip s) {
    switch (s) {
        case Skip::None: return "eligible";
        case Skip::SystemUid: return "system_uid";
        case Skip::Isolated: return "isolated";
        case Skip::ChildZygote: return "child_zygote";
        case Skip::Denylist: return "denylist";
        case Skip::NoName: return "no_name";
        case Skip::HardExcluded: return "hard_excluded";
        case Skip::NoConfig: return "no_config";
        case Skip::Disabled: return "disabled";
        case Skip::StaleBoot: return "stale_boot";
        case Skip::Excluded: return "excluded";
    }
    return "unknown";
}

}  // namespace lsnf
