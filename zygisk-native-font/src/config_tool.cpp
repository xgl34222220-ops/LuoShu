// lsnf-config: compiles the text switches and package lists into runtime/config.bin.
// Runs as root from post-fs-data.sh, before zygote starts. Also used by host tests.
//
//   lsnf-config build --out FILE [--enabled 0|1] [--verbose 0|1] [--boot-id-file FILE]
//                     [--exclude LIST]... [--force LIST]...
//   lsnf-config lookup FILE PACKAGE      prints the bits (decimal)
//   lsnf-config dump FILE                prints flags and every entry
//
// LIST: one package per line; '#' starts a comment; blank lines ignored; invalid names rejected.
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include "config.h"

namespace {

constexpr size_t kMaxEntries = 8192;
constexpr size_t kMaxListBytes = 512 * 1024;

struct Pool {
    char *text[64] = {};
    size_t lists = 0;
    lsnf::ConfigEntryIn entries[kMaxEntries];
    size_t count = 0;
};

int usage() {
    fprintf(stderr,
            "usage: lsnf-config build --out FILE [--enabled 0|1] [--verbose 0|1] [--boot-id-file FILE]\n"
            "                         [--exclude LIST]... [--force LIST]...\n"
            "       lsnf-config lookup FILE PACKAGE\n"
            "       lsnf-config dump FILE\n");
    return 64;
}

char *readFile(const char *path, size_t cap, size_t *len) {
    FILE *f = fopen(path, "rb");
    if (!f) return nullptr;
    char *buf = static_cast<char *>(malloc(cap + 1));
    size_t n = buf ? fread(buf, 1, cap + 1, f) : 0;
    fclose(f);
    if (!buf || n > cap) {
        free(buf);
        return nullptr;
    }
    buf[n] = '\0';
    *len = n;
    return buf;
}

bool addList(Pool &pool, const char *path, uint16_t bits) {
    size_t len = 0;
    char *text = readFile(path, kMaxListBytes, &len);
    if (!text) {
        fprintf(stderr, "lsnf-config: cannot read %s\n", path);
        return false;
    }
    if (pool.lists >= 64) return false;
    pool.text[pool.lists++] = text;
    char *line = text;
    while (line && *line) {
        char *next = strchr(line, '\n');
        if (next) *next++ = '\0';
        char *hash = strchr(line, '#');
        if (hash) *hash = '\0';
        while (*line == ' ' || *line == '\t' || *line == '\r') ++line;
        size_t l = strlen(line);
        while (l > 0 && (line[l - 1] == ' ' || line[l - 1] == '\t' || line[l - 1] == '\r')) line[--l] = '\0';
        if (l > 0) {
            if (pool.count >= kMaxEntries) {
                fprintf(stderr, "lsnf-config: too many entries\n");
                return false;
            }
            pool.entries[pool.count++] = lsnf::ConfigEntryIn{line, bits};
        }
        line = next;
    }
    return true;
}

bool writeAtomic(const char *out, const uint8_t *data, size_t len) {
    char tmp[4096];
    if (snprintf(tmp, sizeof(tmp), "%s.tmp", out) >= int(sizeof(tmp))) return false;
    FILE *f = fopen(tmp, "wb");
    if (!f) return false;
    bool ok = fwrite(data, 1, len, f) == len;
    ok = (fflush(f) == 0) && ok;
    ok = (fclose(f) == 0) && ok;
    if (!ok || rename(tmp, out) != 0) {
        remove(tmp);
        return false;
    }
    return true;
}

int build(int argc, char **argv) {
    static Pool pool;
    const char *out = nullptr;
    const char *bootFile = "/proc/sys/kernel/random/boot_id";
    uint32_t flags = 0;
    for (int i = 0; i < argc; i += 2) {
        const char *a = argv[i];
        const char *v = i + 1 < argc ? argv[i + 1] : nullptr;
        if (!v) return usage();
        if (!strcmp(a, "--out")) out = v;
        else if (!strcmp(a, "--enabled")) flags = !strcmp(v, "1") ? (flags | lsnf::kFlagEnabled) : flags;
        else if (!strcmp(a, "--verbose")) flags = !strcmp(v, "1") ? (flags | lsnf::kFlagVerbose) : flags;
        else if (!strcmp(a, "--boot-id-file")) bootFile = v;
        else if (!strcmp(a, "--exclude")) { if (!addList(pool, v, lsnf::kPkgExclude)) return 65; }
        else if (!strcmp(a, "--force")) { if (!addList(pool, v, lsnf::kPkgForce)) return 65; }
        else return usage();
    }
    if (!out) return usage();
    size_t bootLen = 0;
    char *boot = readFile(bootFile, 256, &bootLen);
    if (!boot) {
        fprintf(stderr, "lsnf-config: cannot read boot id %s\n", bootFile);
        return 66;
    }
    uint64_t hash = lsnf::bootHash(boot, bootLen);
    free(boot);
    static uint8_t blob[lsnf::kConfigMaxBytes];
    size_t len = lsnf::buildConfig(pool.entries, pool.count, flags, hash, blob, sizeof(blob));
    if (len == 0) {
        fprintf(stderr, "lsnf-config: invalid package name or config too large\n");
        return 67;
    }
    if (!writeAtomic(out, blob, len)) {
        fprintf(stderr, "lsnf-config: cannot write %s\n", out);
        return 73;
    }
    printf("lsnf-config: wrote %s (%zu bytes, flags=%u)\n", out, len, flags);
    return 0;
}

bool load(const char *path, char **buf, lsnf::ConfigView *view) {
    size_t len = 0;
    *buf = readFile(path, lsnf::kConfigMaxBytes, &len);
    if (!*buf) return false;
    return lsnf::parseConfig(reinterpret_cast<const uint8_t *>(*buf), len, view);
}

int lookup(const char *path, const char *pkg) {
    char *buf = nullptr;
    lsnf::ConfigView view;
    if (!load(path, &buf, &view)) {
        free(buf);
        fprintf(stderr, "lsnf-config: invalid config %s\n", path);
        return 65;
    }
    printf("%u\n", unsigned(lsnf::lookupPackage(view, pkg, strlen(pkg))));
    free(buf);
    return 0;
}

int dump(const char *path) {
    char *buf = nullptr;
    lsnf::ConfigView view;
    if (!load(path, &buf, &view)) {
        free(buf);
        fprintf(stderr, "lsnf-config: invalid config %s\n", path);
        return 65;
    }
    printf("flags=%u enabled=%d verbose=%d count=%u boot_hash=%016llx\n", view.flags,
           (view.flags & lsnf::kFlagEnabled) ? 1 : 0, (view.flags & lsnf::kFlagVerbose) ? 1 : 0, view.count,
           (unsigned long long)view.bootHash);
    for (uint32_t i = 0; i < view.count; ++i) {
        const uint8_t *e = view.entries + size_t(i) * lsnf::kConfigEntrySize;
        uint32_t off = uint32_t(e[0]) | (uint32_t(e[1]) << 8) | (uint32_t(e[2]) << 16) | (uint32_t(e[3]) << 24);
        unsigned len = unsigned(e[4] | (e[5] << 8)), bits = unsigned(e[6] | (e[7] << 8));
        printf("%.*s\t%u\n", int(len), reinterpret_cast<const char *>(view.strings + off), bits);
    }
    free(buf);
    return 0;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc < 2) return usage();
    if (!strcmp(argv[1], "build")) return build(argc - 2, argv + 2);
    if (!strcmp(argv[1], "lookup") && argc == 4) return lookup(argv[2], argv[3]);
    if (!strcmp(argv[1], "dump") && argc == 3) return dump(argv[2]);
    return usage();
}
