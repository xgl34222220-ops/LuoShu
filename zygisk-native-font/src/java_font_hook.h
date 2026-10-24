// LuoShu native font: Feature 1 JNI glue. Replaces android.graphics.fonts.Font$Builder.nBuild
// (Android 12..16 signature) so fonts an app builds itself are classified at creation time and body
// text fonts are built from the mapped LuoShu face instead. Drawing paths are never touched.
#pragma once

#include <jni.h>

#include <cstdint>

#include "face_table.h"

namespace lsnf {

constexpr const char *kFontBuilderClass = "android/graphics/fonts/Font$Builder";
constexpr const char *kNBuildName = "nBuild";
constexpr const char *kNBuildSig = "(JLjava/nio/ByteBuffer;Ljava/lang/String;Ljava/lang/String;IZI)J";
// Process marker the LSPosed global-font-hook module sets (System.setProperty) once its own Java
// font hooks are live in this process. When present, this module passes every font through.
constexpr const char *kGfhMarkerProperty = "luoshu.gfh.active";

// Registers the replacement. On return methods[i].fnPtr holds the original implementation or
// nullptr when the class / name / signature was not found (Zygisk hookJniNativeMethods contract).
using HookRegistrar = void (*)(void *ctx, JNIEnv *env, const char *className, JNINativeMethod *methods,
                               int count);

struct JavaFontStats {
    uint32_t replaced;
    uint32_t kept;
    uint32_t yielded;
    uint32_t already_ours;
    uint32_t errors;
};

// faces must stay alive (and mapped) for the rest of the process. Returns true when nBuild is now
// replaced; false means nothing is registered and the caller may unload the library.
bool installJavaFontHook(JNIEnv *env, HookRegistrar registrar, void *ctx, const FaceSet *faces, bool verbose);
bool javaFontHookInstalled();
JavaFontStats javaFontStats();

}  // namespace lsnf
