// LuoShu native font: Feature 1 (Java font layer) decisions, free of JNI so they are host tested.
//
//   javaHookGate()       whether to install the Font$Builder.nBuild replacement in this process at all
//   chooseReplacement()  what the replacement does with one font being built
#pragma once

#include <cstddef>
#include <cstdint>

#include "config.h"
#include "face_table.h"
#include "sfnt_verdict.h"

namespace lsnf {

// Android 12 (API 31) introduced the nBuild signature this module replaces. 37 = Android 17, the
// newest release whose sources were checked. Newer releases are skipped unless the user opted in
// (kFlagAllowNewerApi); even then a signature mismatch makes the hook give up on its own.
constexpr int kMinJavaHookApi = 31;
constexpr int kMaxJavaHookApi = 37;

enum class InstallSkip : uint8_t {
    None = 0,        // install
    NotEligible,     // process decision says skip (switch off, excluded, denylist, ...)
    FeatureOff,      // Java font feature switched off
    ApiUnsupported,  // outside Android 12..16 (and no opt-in for newer)
    NoFaces,         // no verified LuoShu face could be mapped
};

InstallSkip javaHookGate(const Decision &decision, uint32_t configFlags, int apiLevel, size_t mappedFaces);
const char *installSkipName(InstallSkip s);

struct ReplaceInput {
    const uint8_t *data = nullptr;
    size_t size = 0;
    uint32_t ttcIndex = 0;
    const char *nameHint = nullptr;  // file path given to Font.Builder, may be empty
    int weight = 400;                // style already resolved by Font.Builder.build()
    bool italic = false;
};

enum class Outcome : uint8_t {
    Keep = 0,     // icon / symbol / monospace / unparsable: original font untouched
    Replace,      // body text: build the LuoShu face instead
    AlreadyOurs,  // the buffer already is one of the mapped LuoShu faces
    NoFace,       // body text but no face available (cannot happen once installed)
};

struct ReplaceChoice {
    Outcome outcome = Outcome::Keep;
    int face = -1;  // index into FaceSet when outcome == Replace
    Verdict verdict = Verdict::Keep;
    Reason reason = Reason::ParseError;
    bool cacheHit = false;
};

ReplaceChoice chooseReplacement(const ReplaceInput &in, const FaceSet &faces);

}  // namespace lsnf
