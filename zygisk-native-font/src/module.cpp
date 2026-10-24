// LuoShu native font: Zygisk entry, shipped inside the main LuoShu module as zygisk/<abi>.so.
//
// The switch is off by default. Without a Zygisk implementation this library is never loaded and
// nothing changes. With Zygisk, the root companion (same library, zygisk_companion_entry) runs
// common/native_font.sh prepare once per boot (and, throttled, again while no LuoShu face was
// usable), which compiles the user switch, the exclude lists and the mounted LuoShu faces into
// zygisk/runtime/*.bin stamped with the current boot id.
//
// For every app process preAppSpecialize reads zygisk/runtime/config.bin through the module dir fd
// and decides whether the process is eligible (switch, boot id, exclude list, built-in skips). When
// it is, and Feature 1 is on (Android 12..16, verified LuoShu faces in runtime/faces.bin), the
// LuoShu body faces are mapped read-only and Font$Builder.nBuild is replaced through Zygisk's
// hookJniNativeMethods. In every other case nothing is installed and the library asks Zygisk to
// dlclose it, so the process is left exactly as it was.
#include <fcntl.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <sys/system_properties.h>
#include <unistd.h>

#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <mutex>

#include "config.h"
#include "face_table.h"
#include "java_font_hook.h"
#include "java_font_policy.h"
#include "log.h"
#include "zygisk.hpp"

namespace {

constexpr const char *kConfigPath = "zygisk/runtime/config.bin";
constexpr const char *kFacesPath = "zygisk/runtime/faces.bin";
// Faces are opened through the mounted system path first (what the app itself would see), then
// relative to the module directory (the main module's own payload).
constexpr const char *kMountedFontDir = "/system/fonts";
constexpr const char *kPayloadFontRel = "system/fonts/";
// Private payload layout (the real partition payload lives under .luoshu-payload).
constexpr const char *kPrivatePayloadFontRel = ".luoshu-payload/system/fonts/";
// Run by the root companion; the module id is fixed (module.prop id=LuoShu).
constexpr const char *kModuleRoot = "/data/adb/modules/LuoShu";
constexpr const char *kPrepareScript = "/data/adb/modules/LuoShu/common/native_font.sh";

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

// True when zygisk/runtime/config.bin parses and carries the current boot id.
bool configFresh(int dir, uint64_t boot);

// Companion requests. Prepare: once per boot. Refresh: the config is fresh but no LuoShu face was
// usable (fonts not yet confirmed when prepare ran); re-run prepare, throttled by the companion.
constexpr uint8_t kReqPrepare = 1;
constexpr uint8_t kReqRefresh = 2;
constexpr int64_t kRefreshIntervalSec = 20;
constexpr int kMaxRefreshesPerBoot = 30;

int64_t monotonicSeconds() {
    struct timespec ts {};
    if (clock_gettime(CLOCK_BOOTTIME, &ts) != 0 && clock_gettime(CLOCK_MONOTONIC, &ts) != 0) return 0;
    return int64_t(ts.tv_sec);
}

// Asks the root companion to prepare this boot's runtime config. Never waits for the prepare
// itself: the companion answers before it starts, so app start-up is not delayed. Processes that
// start before the config exists simply skip (NoConfig / StaleBoot).
void requestPrepare(zygisk::Api *api, uint8_t req = kReqPrepare) {
    int fd = api->connectCompanion();
    if (fd < 0) return;
    uint8_t reply = 0;
    if (write(fd, &req, 1) == 1) (void)read(fd, &reply, 1);
    close(fd);
}

// Root companion: one prepare per boot, plus throttled refreshes (at most one every
// kRefreshIntervalSec, kMaxRefreshesPerBoot per boot, never two at once) while no face is usable.
void companionHandler(int client) {
    static std::mutex lock;
    static uint64_t preparedBoot = 0;
    static int64_t lastRun = 0;
    static int refreshes = 0;
    static bool running = false;
    uint8_t req = 0;
    if (read(client, &req, 1) != 1) return;
    struct stat st {};
    // Only a root-owned, not group/other-writable script inside the module is ever executed.
    bool scriptOk = stat(kPrepareScript, &st) == 0 && st.st_uid == 0 && (st.st_mode & 022) == 0 &&
                    S_ISREG(st.st_mode);
    uint64_t boot = currentBootHash();
    int64_t now = monotonicSeconds();
    bool run = false;
    {
        std::lock_guard<std::mutex> guard(lock);
        if (boot != 0 && preparedBoot != boot) {
            preparedBoot = boot;
            refreshes = 0;
            run = scriptOk && !running;
        } else if (boot != 0 && req == kReqRefresh && scriptOk && !running && refreshes < kMaxRefreshesPerBoot &&
                   now - lastRun >= kRefreshIntervalSec) {
            ++refreshes;
            run = true;
        }
        if (run) {
            running = true;
            lastRun = now;
        }
    }
    uint8_t reply = run ? 1 : 0;
    (void)write(client, &reply, 1);
    if (!run) return;
    pid_t pid = fork();
    if (pid == 0) {
        int devnull = open("/dev/null", O_RDWR | O_CLOEXEC);
        if (devnull >= 0) {
            dup2(devnull, 0);
            dup2(devnull, 1);
            dup2(devnull, 2);
        }
        if (chdir(kModuleRoot) != 0) _exit(126);
        execl("/system/bin/sh", "sh", kPrepareScript, "prepare", static_cast<char *>(nullptr));
        _exit(127);
    }
    if (pid > 0) {
        int status = 0;
        while (waitpid(pid, &status, 0) < 0 && errno == EINTR) {
        }
    }
    std::lock_guard<std::mutex> guard(lock);
    running = false;
    lastRun = monotonicSeconds();
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
            uint64_t boot = currentBootHash();
            if (!view || view->bootHash != boot) requestPrepare(api_);
            d = lsnf::decide(proc, view, boot);
            uint32_t flags = view ? view->flags : 0;
            lsnf::InstallSkip gate = lsnf::javaHookGate(d, flags, apiLevel(), 1);
            size_t mapped = 0;
            if (gate == lsnf::InstallSkip::None) {
                mapped = mapFacesFor(boot);
                gate = lsnf::javaHookGate(d, flags, apiLevel(), mapped);
                // Fonts were not confirmed when this boot's prepare ran: ask for a throttled refresh
                // so later processes pick the faces up instead of yielding for the whole boot.
                if (gate == lsnf::InstallSkip::NoFaces && view && view->bootHash == boot) {
                    requestPrepare(api_, kReqRefresh);
                }
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
        // system_server forks first after boot: start this boot's prepare as early as possible.
        if (!configFresh(api_->getModuleDir(), currentBootHash())) requestPrepare(api_);
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
        size_t mapped = lsnf::mapFaces(table, kMountedFontDir, dir, kPayloadFontRel, &g_faces);
        if (mapped == 0) mapped = lsnf::mapFaces(table, nullptr, dir, kPrivatePayloadFontRel, &g_faces);
        return mapped;
    }

    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

bool configFresh(int dir, uint64_t boot) {
    static uint8_t bytes[64 * 1024];
    lsnf::ConfigView view;
    ssize_t n = readModuleFile(dir, kConfigPath, bytes, sizeof(bytes));
    return n > 0 && lsnf::parseConfig(bytes, size_t(n), &view) && view.bootHash == boot;
}

}  // namespace

REGISTER_ZYGISK_MODULE(NativeFontModule)
REGISTER_ZYGISK_COMPANION(companionHandler)
