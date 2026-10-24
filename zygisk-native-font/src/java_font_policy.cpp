#include "java_font_policy.h"

namespace lsnf {

InstallSkip javaHookGate(const Decision &decision, uint32_t configFlags, int apiLevel, size_t mappedFaces) {
    if (decision.skip != Skip::None) return InstallSkip::NotEligible;
    if (!(configFlags & kFlagJavaFont)) return InstallSkip::FeatureOff;
    if (apiLevel < kMinJavaHookApi) return InstallSkip::ApiUnsupported;
    if (apiLevel > kMaxJavaHookApi && !(configFlags & kFlagAllowNewerApi)) return InstallSkip::ApiUnsupported;
    if (mappedFaces == 0) return InstallSkip::NoFaces;
    return InstallSkip::None;
}

const char *installSkipName(InstallSkip s) {
    switch (s) {
        case InstallSkip::None: return "install";
        case InstallSkip::NotEligible: return "not_eligible";
        case InstallSkip::FeatureOff: return "feature_off";
        case InstallSkip::ApiUnsupported: return "api_unsupported";
        case InstallSkip::NoFaces: return "no_faces";
    }
    return "unknown";
}

ReplaceChoice chooseReplacement(const ReplaceInput &in, const FaceSet &faces) {
    ReplaceChoice c;
    if (!in.data || in.size == 0) return c;
    for (size_t i = 0; i < faces.count; ++i) {
        const MappedFace &f = faces.faces[i];
        if (in.data >= f.addr && in.data < f.addr + f.size) {
            c.outcome = Outcome::AlreadyOurs;
            return c;
        }
    }
    VerdictResult r = classifyCached(in.data, in.size, in.ttcIndex, in.nameHint, &c.cacheHit);
    c.verdict = r.verdict;
    c.reason = r.reason;
    if (r.verdict == Verdict::Keep) return c;
    // ReplaceLatin and ReplaceCjk both map to the LuoShu body set: its faces carry Hans + Latin.
    int idx = pickFace(faces.specs, faces.count, in.weight, in.italic);
    if (idx < 0) {
        c.outcome = Outcome::NoFace;
        return c;
    }
    c.outcome = Outcome::Replace;
    c.face = idx;
    return c;
}

}  // namespace lsnf
