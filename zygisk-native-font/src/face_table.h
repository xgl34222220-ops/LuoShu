// LuoShu native font: the replacement face table (runtime/faces.bin) and the per-process face set.
//
// post-fs-data.sh lists the fonts the main LuoShu module currently applies (verified payload only)
// and lsnf-config writes them here with a content fingerprint. In preAppSpecialize the module opens
// each face through the mounted /system/fonts path (falling back to the main module directory),
// checks size + fingerprint and maps it PROT_READ / MAP_SHARED: the page cache is shared with every
// other process that maps the same inode, nothing is copied.
//
// Layout (little endian):
//   Header { char magic[4] = "LSFT"; u32 version; u32 count; u32 reserved; u64 boot_hash; }   24 bytes
//   Face   { u16 weight; u8 italic; u8 reserved; u32 ttc_index; u64 size; u64 fingerprint;
//            char name[40]; }                                                               64 bytes
// name is a bare file name (no '/'), NUL padded, e.g. "LuoShu-400.ttf".
#pragma once

#include <cstddef>
#include <cstdint>

namespace lsnf {

constexpr uint32_t kFaceTableVersion = 1;
constexpr size_t kFaceHeaderSize = 24;
constexpr size_t kFaceEntrySize = 64;
constexpr size_t kFaceNameMax = 40;  // including the terminating NUL
constexpr size_t kMaxFaces = 8;      // design cap: keeps 32-bit address space use bounded
constexpr size_t kFingerprintSpan = 16 * 1024;

struct FaceSpec {
    uint16_t weight = 400;
    bool italic = false;
    uint32_t ttcIndex = 0;
    uint64_t size = 0;
    uint64_t fingerprint = 0;
    char name[kFaceNameMax] = {};
};

struct FaceTable {
    uint32_t count = 0;
    uint64_t bootHash = 0;
    FaceSpec faces[kMaxFaces];
};

// Fingerprint = FNV-1a 64 over (size, first 16 KiB, last 16 KiB). Cheap enough for every process
// start, strong enough to notice that the file behind a name changed since post-fs-data.
uint64_t faceFingerprint(const uint8_t *data, size_t size);
// Same value from a buffer holding [first 16 KiB][last 16 KiB] of a file of fileSize > 32 KiB.
uint64_t faceFingerprintSpans(const uint8_t *headTail, size_t fileSize);

// Validates a face table blob. False => treat as absent (module installs no hook).
bool parseFaceTable(const uint8_t *data, size_t size, FaceTable *out);

// Writer for lsnf-config and tests. Returns bytes written, 0 on error (bad name, too many faces).
size_t buildFaceTable(const FaceSpec *faces, size_t count, uint64_t bootHash, uint8_t *out, size_t cap);

// "LuoShu-400.ttf" -> weight 400, italic false; "LuoShu-700i.ttf" / "LuoShu-700Italic.ttf" -> italic.
// Only body faces qualify: LuoShuMono-* (monospace) and anything not LuoShu-NNN return false.
bool parseFaceName(const char *name, uint16_t *weight, bool *italic);

// Index of the face that best matches the requested style, or -1 when the table is empty.
// Italic request prefers italic faces (falls back to upright, Skia then synthesizes the slant);
// upright request prefers upright faces. Within the chosen slant the nearest weight wins, ties go
// to the heavier face for weight > 400 and to the lighter one otherwise (CSS-like).
int pickFace(const FaceSpec *faces, size_t count, int weight, bool italic);

// ---- mapped faces (POSIX, also used by host tests) ------------------------------------------------

struct MappedFace {
    const FaceSpec *spec = nullptr;
    const uint8_t *addr = nullptr;
    size_t size = 0;
};

struct FaceSet {
    size_t count = 0;
    MappedFace faces[kMaxFaces];
    FaceSpec specs[kMaxFaces];
};

// Opens every face of the table: first `primaryDir`/<name>, then openat(fallbackDirFd, fallbackRel
// + name) when fallbackDirFd >= 0. A face whose size or fingerprint does not match is skipped.
// Returns the number of mapped faces. fds are closed again; only the read-only mappings stay.
size_t mapFaces(const FaceTable &table, const char *primaryDir, int fallbackDirFd, const char *fallbackRel,
                FaceSet *out);
void unmapFaces(FaceSet *set);

}  // namespace lsnf
