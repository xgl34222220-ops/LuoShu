// LuoShu native font: Zygisk entry (N1 skeleton).
//
// N1 installs no hook at all. For every app process it only reads runtime/config.bin through the
// module directory fd, decides whether the process would be eligible (switch, boot id, exclude
// list, built-in skips) and, when verbose logging is on, writes one logcat line. The library then
// asks Zygisk to dlclose it, so the process is left exactly as it was.
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <cstring>

#include "config.h"
#include "log.h"
#include "zygisk.hpp"

namespace {

constexpr const char *kConfigPath = "runtime/config.bin";

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

uint64_t currentBootHash() {
    int fd = open("/proc/sys/kernel/random/boot_id", O_RDONLY | O_CLOEXEC);
    if (fd < 0) return 0;
    char buf[64];
    ssize_t n = read(fd, buf, sizeof(buf));
    close(fd);
    return n > 0 ? lsnf::bootHash(buf, size_t(n)) : 0;
}

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

        // Fast skips first: they need neither the process name nor the config file.
        lsnf::Decision d = lsnf::decide(proc, nullptr, 0);
        if (d.skip == lsnf::Skip::NoName) {
            const char *name = args->nice_name ? env_->GetStringUTFChars(args->nice_name, nullptr) : nullptr;
            proc.niceName = name;
            ConfigBuffer cfg;
            const lsnf::ConfigView *view = loadConfig(cfg) ? &cfg.view : nullptr;
            d = lsnf::decide(proc, view, view ? currentBootHash() : 0);
            if (d.verbose) {
                LSNF_LOGI("pkg=%s uid=%d decision=%s bits=%u hooks=none(N1)", name ? name : "?", int(proc.uid),
                          lsnf::skipName(d.skip), unsigned(d.bits));
            }
            if (name) env_->ReleaseStringUTFChars(args->nice_name, name);
        }
        // N1: nothing is hooked, so unloading is always safe and keeps the process pristine.
        api_->setOption(zygisk::Option::DLCLOSE_MODULE_LIBRARY);
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
        int dir = api_->getModuleDir();
        if (dir < 0) return false;
        int fd = openat(dir, kConfigPath, O_RDONLY | O_CLOEXEC | O_NOFOLLOW);
        if (fd < 0) return false;
        struct stat st {};
        bool ok = fstat(fd, &st) == 0 && st.st_size > 0 && size_t(st.st_size) <= sizeof(cfg.bytes);
        ssize_t n = ok ? readAll(fd, cfg.bytes, size_t(st.st_size)) : -1;
        close(fd);
        return n == st.st_size && lsnf::parseConfig(cfg.bytes, size_t(n), &cfg.view);
    }

    zygisk::Api *api_ = nullptr;
    JNIEnv *env_ = nullptr;
};

}  // namespace

REGISTER_ZYGISK_MODULE(NativeFontModule)
