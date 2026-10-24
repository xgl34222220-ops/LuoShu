// LuoShu native font: runtime config (runtime/config.bin) format, reader, writer and the
// per-process decision. Pure C++, no Android dependencies, unit tested on the host.
//
// Layout (little endian):
//   Header  { char magic[4] = "LSNF"; u32 version; u32 flags; u32 count;
//             u64 boot_hash; u32 strings_size; u32 reserved; }        32 bytes
//   Entry   { u32 name_off; u16 name_len; u16 bits; } x count         sorted by name (memcmp)
//   strings { package names, not NUL terminated }
#pragma once

#include <cstddef>
#include <cstdint>

namespace lsnf {

constexpr uint32_t kConfigVersion = 1;
constexpr size_t kConfigHeaderSize = 32;
constexpr size_t kConfigEntrySize = 8;
constexpr size_t kConfigMaxBytes = 1u << 20;  // reader refuses anything larger
constexpr size_t kPackageMaxLen = 255;

// Header flags.
enum ConfigFlag : uint32_t {
    kFlagEnabled = 1u << 0,  // user switch; off by default
    kFlagVerbose = 1u << 1,  // log one line per decided process
    kFlagJavaFont = 1u << 2,       // Feature 1: Font$Builder.nBuild replacement (needs kFlagEnabled)
    kFlagAllowNewerApi = 1u << 3,  // let Feature 1 try releases newer than Android 16
};

// Per-package bits.
enum PackageBit : uint16_t {
    kPkgExclude = 1u << 0,  // never touch this package
    kPkgForce = 1u << 1,    // reserved for a later "force on" list (N5); parsed, not acted on yet
};

uint64_t bootHash(const char *bootId, size_t len);  // trims whitespace, FNV-1a 64

struct ConfigView {
    const uint8_t *data = nullptr;
    size_t size = 0;
    uint32_t flags = 0;
    uint32_t count = 0;
    uint64_t bootHash = 0;
    const uint8_t *entries = nullptr;
    const uint8_t *strings = nullptr;
    uint32_t stringsSize = 0;
};

// Validates the whole blob (header, bounds of every entry, sort order). False => treat as absent.
bool parseConfig(const uint8_t *data, size_t size, ConfigView *out);

// Binary search; returns the bits for pkg or 0 when not listed.
uint16_t lookupPackage(const ConfigView &cfg, const char *pkg, size_t len);

// Writer used by the on-device lsnf-config tool and by tests.
struct ConfigEntryIn {
    const char *name;
    uint16_t bits;
};
// Sorts and merges duplicates (bits OR-ed). Returns bytes written, 0 on error / too small.
size_t buildConfig(ConfigEntryIn *entries, size_t count, uint32_t flags, uint64_t bootHash, uint8_t *out,
                   size_t cap);

// ---- process decision ---------------------------------------------------------------

struct ProcessInfo {
    int32_t uid = 0;
    bool childZygote = false;
    bool onDenylist = false;
    const char *niceName = nullptr;  // "com.foo" or "com.foo:remote"
};

enum class Skip : uint8_t {
    None = 0,        // eligible; features still have their own gates (java_font_policy.h)
    SystemUid,       // app id < 10000
    Isolated,        // app id 90000..99999 (isolated / app zygote children)
    ChildZygote,
    Denylist,        // root manager asked to hide from this process
    NoName,
    HardExcluded,    // built-in: SystemUI, the app itself is never a target
    NoConfig,        // config.bin missing / invalid
    Disabled,        // user switch off
    StaleBoot,       // config was written for another boot
    Excluded,        // listed in the exclude list
};

struct Decision {
    Skip skip = Skip::NoConfig;
    uint16_t bits = 0;
    bool verbose = false;
};

Decision decide(const ProcessInfo &proc, const ConfigView *cfg, uint64_t currentBootHash);
const char *skipName(Skip s);

// Length of the package part of a process name ("com.foo:remote" -> 7).
size_t packageLength(const char *niceName);

}  // namespace lsnf
