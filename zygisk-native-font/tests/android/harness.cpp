// Emulator integration harness (test only, never packaged into the module ZIP).
//
// Installs the same Feature 1 hook the Zygisk module installs, but through plain RegisterNatives,
// inside an app_process started from adb shell. The registrar mimics Zygisk's hookJniNativeMethods
// contract: methods[i].fnPtr receives the original implementation. The original is read from the
// ArtMethod of Font$Builder.nBuild (data_ field) and accepted only when dladdr() places it inside
// libhwui; otherwise a recorder stub stands in and the Java side calls nBuild by reflection.
#include <dlfcn.h>
#include <fcntl.h>
#include <jni.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <unistd.h>

#include <atomic>
#include <cstdio>
#include <cstring>

#include "face_table.h"
#include "java_font_hook.h"

namespace {

lsnf::FaceSet g_faces;
void *g_realOrig = nullptr;
std::atomic<const void *> g_lastBuffer{nullptr};
std::atomic<int> g_lastWeight{-1}, g_lastItalic{-1}, g_lastTtc{-1};

jlong JNICALL recorderNBuild(JNIEnv *env, jclass, jlong, jobject buffer, jstring, jstring, jint weight,
                             jboolean italic, jint ttc) {
    g_lastBuffer.store(buffer ? env->GetDirectBufferAddress(buffer) : nullptr);
    g_lastWeight.store(weight);
    g_lastItalic.store(italic ? 1 : 0);
    g_lastTtc.store(ttc);
    return 0x5151;
}

void harnessRegistrar(void *, JNIEnv *env, const char *cls, JNINativeMethod *methods, int count) {
    jclass c = env->FindClass(cls);
    if (!c) {
        env->ExceptionClear();
        for (int i = 0; i < count; ++i) methods[i].fnPtr = nullptr;
        return;
    }
    void *orig = g_realOrig ? g_realOrig : reinterpret_cast<void *>(recorderNBuild);
    if (env->RegisterNatives(c, methods, count) != JNI_OK) {
        env->ExceptionClear();
        orig = nullptr;
    }
    for (int i = 0; i < count; ++i) methods[i].fnPtr = orig;
    env->DeleteLocalRef(c);
}

bool mapFaceFile(const char *path, uint16_t weight, bool italic) {
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return false;
    struct stat st {};
    if (fstat(fd, &st) != 0) {
        close(fd);
        return false;
    }
    void *p = mmap(nullptr, size_t(st.st_size), PROT_READ, MAP_SHARED, fd, 0);
    close(fd);
    if (p == MAP_FAILED) return false;
    size_t k = g_faces.count++;
    lsnf::FaceSpec &s = g_faces.specs[k];
    s.weight = weight;
    s.italic = italic;
    s.size = uint64_t(st.st_size);
    s.fingerprint = lsnf::faceFingerprint(static_cast<const uint8_t *>(p), size_t(st.st_size));
    g_faces.faces[k].spec = &s;
    g_faces.faces[k].addr = static_cast<const uint8_t *>(p);
    g_faces.faces[k].size = size_t(st.st_size);
    return true;
}

}  // namespace

extern "C" {

// Returns "real:<lib>" when the libhwui original was found, "stub" otherwise.
JNIEXPORT jstring JNICALL Java_LsnfHarness_probeOriginal(JNIEnv *env, jclass, jlong artMethod) {
    g_realOrig = nullptr;
    if (artMethod != 0) {
        // ArtMethod: declaring_class_ u32, access_flags_ u32, dex_method_index_ u32, method_index_ u16,
        // hotness/imt u16, then ptr_sized_fields_ { data_, entry_point_ } (Android 12..16).
        void *data = *reinterpret_cast<void **>(static_cast<uintptr_t>(artMethod) + 16);
        Dl_info info{};
        if (data && dladdr(data, &info) && info.dli_fname && strstr(info.dli_fname, "libhwui")) {
            g_realOrig = data;
            char buf[256];
            snprintf(buf, sizeof(buf), "real:%s", info.dli_fname);
            return env->NewStringUTF(buf);
        }
    }
    return env->NewStringUTF("stub");
}

JNIEXPORT jboolean JNICALL Java_LsnfHarness_install(JNIEnv *env, jclass, jstring regular, jstring bold) {
    const char *r = env->GetStringUTFChars(regular, nullptr);
    const char *b = env->GetStringUTFChars(bold, nullptr);
    bool ok = mapFaceFile(r, 400, false) && mapFaceFile(b, 700, false);
    env->ReleaseStringUTFChars(regular, r);
    env->ReleaseStringUTFChars(bold, b);
    if (!ok) return JNI_FALSE;
    return lsnf::installJavaFontHook(env, harnessRegistrar, nullptr, &g_faces, false) ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jlong JNICALL Java_LsnfHarness_faceAddress(JNIEnv *, jclass, jint idx) {
    return idx >= 0 && size_t(idx) < g_faces.count ? jlong(reinterpret_cast<uintptr_t>(g_faces.faces[idx].addr)) : 0;
}

JNIEXPORT jlong JNICALL Java_LsnfHarness_bufferAddress(JNIEnv *env, jclass, jobject buffer) {
    return buffer ? jlong(reinterpret_cast<uintptr_t>(env->GetDirectBufferAddress(buffer))) : 0;
}

JNIEXPORT jlongArray JNICALL Java_LsnfHarness_lastCall(JNIEnv *env, jclass) {
    jlong v[4] = {jlong(reinterpret_cast<uintptr_t>(g_lastBuffer.load())), g_lastWeight.load(), g_lastItalic.load(),
                  g_lastTtc.load()};
    jlongArray a = env->NewLongArray(4);
    env->SetLongArrayRegion(a, 0, 4, v);
    return a;
}

JNIEXPORT jintArray JNICALL Java_LsnfHarness_stats(JNIEnv *env, jclass) {
    lsnf::JavaFontStats s = lsnf::javaFontStats();
    jint v[5] = {jint(s.replaced), jint(s.kept), jint(s.yielded), jint(s.already_ours), jint(s.errors)};
    jintArray a = env->NewIntArray(5);
    env->SetIntArrayRegion(a, 0, 5, v);
    return a;
}

}  // extern "C"
