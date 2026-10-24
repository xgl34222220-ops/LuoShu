// LuoShu native font: Zygisk entry.
//
// For every app process preAppSpecialize reads runtime/config.bin through the module directory fd
// and decides whether the process is eligible (switch, boot id, exclude list, built-in skips). When
// it is, and Feature 1 is on (Android 12..16, verified LuoShu faces in runtime/faces.bin), the
// LuoShu body faces are mapped read-only and Font$Builder.nBuild is replaced through Zygisk's
// hookJniNativeMethods. In every other case nothing is installed and the library asks Zygisk to
// dlclose it, so the process is left exactly as it was.
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/system_properties.h>
#include <unistd.h>

#include <cstdlib>
#include <cstring>

#include "config.h"
#include "face_table.h"
#include "java_font_hook.h"
#include "java_font_policy.h"
#include "log.h"
#include "zygisk.hpp"

namespace {

constexpr const char *kConfigPath = "runtime/config.bin";
constexpr const char *kFacesPath = "runtime/faces.bin";
// Faces are opened through the mounted system path first (what the app itself would see), then
// relative to this module's directory inside the main module's payload.
constexpr const char *kMountedFontDir = "/system/fonts";
constexpr const char *kPayloadFontRel = "../LuoShu/system/fonts/";

ssize_t readAll(int fd, uint8_t *buf, size_t cap) {
    size_t got = 0;
    while (got < cap) {
        ssize_t n = pread(fd, buf + got, cap - got, off_t(got));
        if (n < 0) return -1;
        if (n == 0) break;
        got += size_t(n);
    }
    return ssize_t(got);
}

ssize_t readModuleFile(int dir, const char *rel, uint8_t *buf, size_t cap) {
    if (dir < 0) return -1;
    int fd = openat(dir, rel, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
    if (fd < 0) return -1;
    struct stat st {};
    bool ok = fstat(fd, &st) == 0 && st.st_size > 0 && size_t(st.st_size) <= cap;
    ssize_t n = ok ? readAll(fd, buf, size_t(st.st_size)) : -1;
    close(fd);
    return (ok && n == st.st_size) ? n : -1;
}

uint64_t currentBootHash() {
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    char buf[64];
    ssize_t n = read(fd, buf, sizeof(buf));
    close(fd);
    return n > 0 ? lsnf::bootHash(buf, size_t(n)) : 0;
}

int apiLevel() {
    char v[PROP_VALUE_MAX] = {};
    if (__system_property_get("ro.build.version.sdk", v) <= 0) return 0;
    return atoi(v);
}

void zygiskRegistrar(void *ctx, JNIEnv *env, const char *cls, JNINativeMethod *methods, int count) {
    static_cast<zygisk::Api *>(ctx)->hookJniNativeMethods(env, cls, methods, count);
}

// Lives for the whole process once the hook is installed (the mappings back the font buffers).
lsnf::FaceSet g_faces;

class NativeFontModule : public zygisk::ModuleBase {
public:
    void onLoad(zygisk::Api *api, JNIEnv *env) override {
        api_ = api;
        env_ = env;
    }

    void preAppSpecialize(zygisk::AppSpecializeArgs *args) override {
        lsnf::ProcessInfo proc;
        proc.uid = args->uid;
        proc.childZygote = args->is_child_zygote && *args->is_child_zygote;
        proc.onDenylist = (api_->getFlags() & zygisk::StateFlag::PROCESS_ON_DENYLIST) != 0;

        bool hooked = false;
        // Fast skips first: they need neither the process name nor the config file.
        lsnf::Decision d = lsnf::decide(proc, nullptr, 0);
        if (d.skip == lsnf::Skip::NoName) {
            const char *name = args->nice_name ? env_->GetStringUTFChars(args->nice_name, nullptr) : nullptr;
            proc.niceName = name;
            ConfigBuffer cfg;
            const lsnf::ConfigView *view = loadConfig(cfg) ? &cfg.view : nullptr;
            uint64_t boot = view ? currentBootHash() : 0;
            d = lsnf::decide(proc, view, boot);
            uint32_t flags = view ? view->flags : 0;
            lsnf::InstallSkip gate = lsnf::javaHookGate(d, flags, apiLevel(), 1);
            size_t mapped = 0;
            if (gate == lsnf::InstallSkip::None) {
                mapped = mapFacesFor(boot);
                gate = lsnf::javaHookGate(d, flags, apiLevel(), mapped);
            }
            if (gate == lsnf::InstallSkip::None) {
                hooked = lsnf::installJavaFontHook(env_, zygiskRegistrar, api_, &g_faces, d.verbose);
                if (!hooked) lsnf::unmapFaces(&g_faces);
            }
            if (d.verbose) {
                LSNF_LOGI("pkg=%s uid=%d decision=%s bits=%u java_font=%s faces=%zu jni=%s", name ? name : "?",
                          int(proc.uid), lsnf::skipName(d.skip), unsigned(d.bits), lsnf::installSkipName(gate),
                          mapped, hooked ? "ok" : (gate == lsnf::InstallSkip::None ? "unavailable" : "none"));
            }
            if (name) env_->ReleaseStringUTFChars(args->nice_name, name);
        }
        // Nothing registered => unloading is safe and keeps the process pristine. Once nBuild points
        // into this library it must stay loaded.
        if (!hooked) api_->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
    }

    void preServerSpecialize(zygisk::ServerSpecializeArgs *) override {
        api_->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
    }

private:
    struct ConfigBuffer {
        uint8_t bytes[64 * 1024];
        lsnf::ConfigView view;
    };

    bool loadConfig(ConfigBuffer &cfg) {
        ssize_t n = readModuleFile(api_->getModuleDir(), kConfigPath, cfg.bytes, sizeof(cfg.bytes));
        return n > 0 && lsnf::parseConfig(cfg.bytes, size_t(n), &cfg.view);
    }

    size_t mapFacesFor(uint64_t boot) {
        int dir = api_->getModuleDir();
        uint8_t buf[lsnf::kFaceHeaderSize + lsnf::kMaxFaces * lsnf::kFaceEntrySize];
        ssize_t n = readModuleFile(dir, kFacesPath, buf, sizeof(buf));
        lsnf::FaceTable table;
        if (n <= 0 || !lsnf::parseFaceTable(buf, size_t(n), &table) || table.bootHash != boot) return 0;
        return lsnf::mapFaces(table, kMountedFontDir, dir, kPayloadFontRel, &g_faces);
    }

    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

}  // namespace

REGISTER_ZYGISK_MODULE(NativeFontModule)
