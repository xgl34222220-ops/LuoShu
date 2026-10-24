#include "face_table.h"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstdio>
#include <cstring>

namespace lsnf {
namespace {

constexpr char kMagic[4] = {'L', 'S', 'F', 'T'};

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

uint64_t fnv(uint64_t h, const uint8_t *p, size_t n) {
    for (size_t i = 0; i < n; ++i) {
        h ^= p[i];
        h *= 0x100000001B3ull;
    }
    return h;
}

bool validFaceName(const char *s, size_t len) {
    if (len == 0 || len >= kFaceNameMax) return false;
    if (s[0] == '.') return false;
    for (size_t i = 0; i < len; ++i) {
        unsigned char c = (unsigned char)s[i];
        bool ok = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.' ||
                  c == '_' || c == '-';
        if (!ok) return false;
    }
    return true;
}

bool openAndMap(int fd, const FaceSpec &spec, MappedFace *out) {
    struct stat st {};
    if (fstat(fd, &st) != 0 || !S_ISREG(st.st_mode) || uint64_t(st.st_size) != spec.size || spec.size < 12) {
        return false;
    }
    void *p = mmap(nullptr, size_t(spec.size), PROT_READ, MAP_SHARED, fd, 0);
    if (p == MAP_FAILED) return false;
    const uint8_t *addr = static_cast<const uint8_t *>(p);
    if (faceFingerprint(addr, size_t(spec.size)) != spec.fingerprint) {
        munmap(p, size_t(spec.size));
        return false;
    }
    out->addr = addr;
    out->size = size_t(spec.size);
    return true;
}

}  // namespace

uint64_t faceFingerprint(const uint8_t *data, size_t size) {
    uint8_t sz[8];
    wr64(sz, uint64_t(size));
    uint64_t h = fnv(0xCBF29CE484222325ull, sz, sizeof(sz));
    if (!data || size == 0) return h;
    size_t head = size < kFingerprintSpan ? size : kFingerprintSpan;
    h = fnv(h, data, head);
    if (size > kFingerprintSpan) {
        size_t tail = size - kFingerprintSpan < kFingerprintSpan ? size - kFingerprintSpan : kFingerprintSpan;
        h = fnv(h, data + size - tail, tail);
    }
    return h;
}

uint64_t faceFingerprintSpans(const uint8_t *headTail, size_t fileSize) {
    uint8_t sz[8];
    wr64(sz, uint64_t(fileSize));
    uint64_t h = fnv(0xCBF29CE484222325ull, sz, sizeof(sz));
    return fnv(h, headTail, 2 * kFingerprintSpan);
}

bool parseFaceTable(const uint8_t *data, size_t size, FaceTable *out) {
    if (!data || !out || size < kFaceHeaderSize) return false;
    if (memcmp(data, kMagic, 4) != 0 || rd32(data + 4) != kFaceTableVersion) return false;
    uint32_t count = rd32(data + 8);
    if (count == 0 || count > kMaxFaces) return false;
    if (size != kFaceHeaderSize + size_t(count) * kFaceEntrySize) return false;
    FaceTable t;
    t.count = count;
    t.bootHash = rd64(data + 16);
    for (uint32_t i = 0; i < count; ++i) {
        const uint8_t *e = data + kFaceHeaderSize + size_t(i) * kFaceEntrySize;
        FaceSpec &f = t.faces[i];
        f.weight = rd16(e);
        if (f.weight < 1 || f.weight > 1000 || e[2] > 1) return false;
        f.italic = e[2] == 1;
        f.ttcIndex = rd32(e + 4);
        f.size = rd64(e + 8);
        f.fingerprint = rd64(e + 16);
        memcpy(f.name, e + 24, kFaceNameMax);
        size_t len = strnlen(f.name, kFaceNameMax);
        if (len == kFaceNameMax || !validFaceName(f.name, len)) return false;
        for (size_t k = len; k < kFaceNameMax; ++k) {
            if (f.name[k] != '\0') return false;
        }
        if (f.size < 12) return false;
    }
    *out = t;
    return true;
}

size_t buildFaceTable(const FaceSpec *faces, size_t count, uint64_t bootHash, uint8_t *out, size_t cap) {
    if (!faces || count == 0 || count > kMaxFaces) return 0;
    size_t total = kFaceHeaderSize + count * kFaceEntrySize;
    if (!out || cap < total) return 0;
    memset(out, 0, total);
    memcpy(out, kMagic, 4);
    wr32(out + 4, kFaceTableVersion);
    wr32(out + 8, uint32_t(count));
    wr64(out + 16, bootHash);
    for (size_t i = 0; i < count; ++i) {
        const FaceSpec &f = faces[i];
        size_t len = strnlen(f.name, kFaceNameMax);
        if (len == kFaceNameMax || !validFaceName(f.name, len) || f.weight < 1 || f.weight > 1000 || f.size < 12) {
            return 0;
        }
        uint8_t *e = out + kFaceHeaderSize + i * kFaceEntrySize;
        wr16(e, f.weight);
        e[2] = f.italic ? 1 : 0;
        wr32(e + 4, f.ttcIndex);
        wr64(e + 8, f.size);
        wr64(e + 16, f.fingerprint);
        memcpy(e + 24, f.name, len);
    }
    return total;
}

bool parseFaceName(const char *name, uint16_t *weight, bool *italic) {
    static const char kPrefix[] = "LuoShu-";
    const size_t plen = sizeof(kPrefix) - 1;
    if (!name || strncmp(name, kPrefix, plen) != 0) return false;
    const char *p = name + plen;
    if (!(p[0] >= '1' && p[0] <= '9' && p[1] >= '0' && p[1] <= '9' && p[2] >= '0' && p[2] <= '9')) return false;
    int w = (p[0] - '0') * 100 + (p[1] - '0') * 10 + (p[2] - '0');
    p += 3;
    bool it = false;
    if (strncmp(p, "Italic", 6) == 0) {
        it = true;
        p += 6;
    } else if (*p == 'i') {
        it = true;
        ++p;
    }
    if (strcmp(p, ".ttf") != 0 && strcmp(p, ".otf") != 0) return false;
    if (w > 1000) return false;
    if (weight) *weight = uint16_t(w);
    if (italic) *italic = it;
    return true;
}

int pickFace(const FaceSpec *faces, size_t count, int weight, bool italic) {
    if (!faces || count == 0) return -1;
    bool haveSlant = false;
    for (size_t i = 0; i < count; ++i) haveSlant = haveSlant || faces[i].italic == italic;
    int best = -1;
    int bestDist = 0;
    for (size_t i = 0; i < count; ++i) {
        if (haveSlant && faces[i].italic != italic) continue;
        int w = faces[i].weight;
        int dist = w > weight ? w - weight : weight - w;
        if (best < 0 || dist < bestDist) {
            best = int(i);
            bestDist = dist;
        } else if (dist == bestDist) {
            int bw = faces[best].weight;
            bool preferHeavier = weight > 400;
            if (preferHeavier ? w > bw : w < bw) best = int(i);
        }
    }
    return best;
}

size_t mapFaces(const FaceTable &table, const char *primaryDir, int fallbackDirFd, const char *fallbackRel,
                FaceSet *out) {
    if (!out) return 0;
    *out = FaceSet();
    for (uint32_t i = 0; i < table.count && out->count < kMaxFaces; ++i) {
        const FaceSpec &spec = table.faces[i];
        char path[512];
        MappedFace mf;
        bool ok = false;
        if (primaryDir && snprintf(path, sizeof(path), "%s/%s", primaryDir, spec.name) < int(sizeof(path))) {
            int fd = open(path, O_RDONLY | O_CLOEXEC);
            if (fd >= 0) {
                ok = openAndMap(fd, spec, &mf);
                close(fd);
            }
        }
        if (!ok && fallbackDirFd >= 0 && fallbackRel &&
            snprintf(path, sizeof(path), "%s%s", fallbackRel, spec.name) < int(sizeof(path))) {
            int fd = openat(fallbackDirFd, path, O_RDONLY | O_CLOEXEC);
            if (fd >= 0) {
                ok = openAndMap(fd, spec, &mf);
                close(fd);
            }
        }
        if (!ok) continue;
        size_t k = out->count++;
        out->specs[k] = spec;
        out->faces[k] = mf;
        out->faces[k].spec = &out->specs[k];
    }
    return out->count;
}

void unmapFaces(FaceSet *set) {
    if (!set) return;
    for (size_t i = 0; i < set->count; ++i) {
        if (set->faces[i].addr) munmap(const_cast<uint8_t *>(set->faces[i].addr), set->faces[i].size);
    }
    *set = FaceSet();
}

}  // namespace lsnf
