#include "java_font_hook.h"

#include <atomic>
#include <cstring>

#include "java_font_policy.h"
#include "log.h"

namespace lsnf {
namespace {

using NBuildFn = jlong (*)(JNIEnv *, jclass, jlong, jobject, jstring, jstring, jint, jboolean, jint);

std::atomic<NBuildFn> g_orig{nullptr};
const FaceSet *g_faces = nullptr;
bool g_verbose = false;
std::atomic<jobject> g_buffers[kMaxFaces];  // DirectByteBuffer over each mapped face, made once
std::atomic<int> g_yield{0};                // 1 once the global-font-hook marker was seen
jclass g_systemClass = nullptr;
jmethodID g_getProperty = nullptr;
jstring g_markerKey = nullptr;

std::atomic<uint32_t> g_replaced{0}, g_kept{0}, g_yielded{0}, g_ours{0}, g_errors{0};

bool clearException(JNIEnv *env) {
    if (!env->ExceptionCheck()) return false;
    env->ExceptionClear();
    return true;
}

// Reads System.getProperty("luoshu.gfh.active"). Any failure counts as "not active". Once seen the
// answer is latched for the life of the process (the marker is never removed).
bool yieldToGlobalFontHook(JNIEnv *env) {
    if (g_yield.load(std::memory_order_relaxed) == 1) return true;
    if (!g_systemClass || !g_getProperty || !g_markerKey) return false;
    jobject v = env->CallStaticObjectMethod(g_systemClass, g_getProperty, g_markerKey);
    if (clearException(env) || !v) return false;
    bool active = false;
    const char *s = env->GetStringUTFChars(static_cast<jstring>(v), nullptr);
    if (s) {
        active = strcmp(s, "1") == 0 || strcmp(s, "true") == 0;
        env->ReleaseStringUTFChars(static_cast<jstring>(v), s);
    }
    clearException(env);
    env->DeleteLocalRef(v);
    if (active) g_yield.store(1, std::memory_order_relaxed);
    return active;
}

jobject faceBuffer(JNIEnv *env, int idx) {
    jobject cur = g_buffers[idx].load(std::memory_order_acquire);
    if (cur) return cur;
    const MappedFace &f = g_faces->faces[idx];
    jobject local = env->NewDirectByteBuffer(const_cast<uint8_t *>(f.addr), jlong(f.size));
    if (clearException(env) || !local) return nullptr;
    jobject global = env->NewGlobalRef(local);
    env->DeleteLocalRef(local);
    if (!global) return nullptr;
    jobject expected = nullptr;
    if (!g_buffers[idx].compare_exchange_strong(expected, global, std::memory_order_acq_rel)) {
        env->DeleteGlobalRef(global);
        return expected;
    }
    return global;
}

void readHint(JNIEnv *env, jstring path, char *out, size_t cap) {
    out[0] = '\0';
    if (!path) return;
    jsize chars = env->GetStringLength(path);
    jsize bytes = env->GetStringUTFLength(path);
    if (chars <= 0 || bytes <= 0 || size_t(bytes) >= cap) return;
    env->GetStringUTFRegion(path, 0, chars, out);
    if (clearException(env)) {
        out[0] = '\0';
        return;
    }
    out[bytes] = '\0';
}

jlong JNICALL hookedNBuild(JNIEnv *env, jclass clazz, jlong builderPtr, jobject buffer, jstring filePath,
                           jstring localeList, jint weight, jboolean italic, jint ttcIndex) {
    NBuildFn orig = g_orig.load(std::memory_order_acquire);
    if (buffer && g_faces) {
        if (yieldToGlobalFontHook(env)) {
            g_yielded.fetch_add(1, std::memory_order_relaxed);
        } else {
            void *addr = env->GetDirectBufferAddress(buffer);
            jlong cap = env->GetDirectBufferCapacity(buffer);
            if (clearException(env) || !addr || cap <= 0) {
                g_errors.fetch_add(1, std::memory_order_relaxed);
            } else {
                char hint[512];
                readHint(env, filePath, hint, sizeof(hint));
                ReplaceInput in;
                in.data = static_cast<const uint8_t *>(addr);
                in.size = size_t(cap);
                in.ttcIndex = ttcIndex < 0 ? 0xFFFFFFFFu : uint32_t(ttcIndex);
                in.nameHint = hint[0] ? hint : nullptr;
                in.weight = weight;
                in.italic = italic == JNI_TRUE;
                ReplaceChoice c = chooseReplacement(in, *g_faces);
                if (c.outcome == Outcome::Replace) {
                    jobject nb = faceBuffer(env, c.face);
                    if (nb) {
                        uint32_t n = g_replaced.fetch_add(1, std::memory_order_relaxed);
                        if (g_verbose && n == 0) {
                            LSNF_LOGI("java_font: first replacement %s -> %s (w=%d i=%d %s)", hint[0] ? hint : "-",
                                      g_faces->specs[c.face].name, int(weight), int(italic),
                                      verdictName(c.verdict));
                        }
                        // weight / italic stay what the app asked for; only the bytes and index change.
                        return orig(env, clazz, builderPtr, nb, filePath, localeList, weight, italic,
                                    jint(g_faces->specs[c.face].ttcIndex));
                    }
                    g_errors.fetch_add(1, std::memory_order_relaxed);
                } else if (c.outcome == Outcome::AlreadyOurs) {
                    g_ours.fetch_add(1, std::memory_order_relaxed);
                } else {
                    g_kept.fetch_add(1, std::memory_order_relaxed);
                }
            }
        }
    }
    return orig(env, clazz, builderPtr, buffer, filePath, localeList, weight, italic, ttcIndex);
}

bool prepareMarkerLookup(JNIEnv *env) {
    jclass sys = env->FindClass("java/lang/System");
    if (clearException(env) || !sys) return false;
    jmethodID gp = env->GetStaticMethodID(sys, "getProperty", "(Ljava/lang/String;)Ljava/lang/String;");
    jstring key = gp ? env->NewStringUTF(kGfhMarkerProperty) : nullptr;
    if (clearException(env) || !gp || !key) {
        env->DeleteLocalRef(sys);
        if (key) env->DeleteLocalRef(key);
        return false;
    }
    g_systemClass = static_cast<jclass>(env->NewGlobalRef(sys));
    g_markerKey = static_cast<jstring>(env->NewGlobalRef(key));
    g_getProperty = gp;
    env->DeleteLocalRef(sys);
    env->DeleteLocalRef(key);
    return g_systemClass && g_markerKey;
}

}  // namespace

bool installJavaFontHook(JNIEnv *env, HookRegistrar registrar, void *ctx, const FaceSet *faces, bool verbose) {
    if (!env || !registrar || !faces || faces->count == 0 || g_orig.load()) return false;
    // Without the marker lookup the module could not yield to global-font-hook: install nothing.
    if (!prepareMarkerLookup(env)) return false;
    g_faces = faces;
    g_verbose = verbose;
    JNINativeMethod m[] = {{kNBuildName, kNBuildSig, reinterpret_cast<void *>(hookedNBuild)}};
    registrar(ctx, env, kFontBuilderClass, m, 1);
    clearException(env);
    if (!m[0].fnPtr || m[0].fnPtr == reinterpret_cast<void *>(hookedNBuild)) {
        // Signature not found (ROM changed the JNI table, or another release): nothing registered.
        g_faces = nullptr;
        return false;
    }
    g_orig.store(reinterpret_cast<NBuildFn>(m[0].fnPtr), std::memory_order_release);
    return true;
}

bool javaFontHookInstalled() { return g_orig.load(std::memory_order_acquire) != nullptr; }

JavaFontStats javaFontStats() {
    return JavaFontStats{g_replaced.load(), g_kept.load(), g_yielded.load(), g_ours.load(), g_errors.load()};
}

}  // namespace lsnf
