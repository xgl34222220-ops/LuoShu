// Feature 1 decisions on the host: install gate and per-font replacement over the generated corpus.
#include <cstring>
#include <string>

#include "java_font_policy.h"
#include "test_util.h"

using namespace lsnf;

namespace {

void testGate() {
    Decision ok;
    ok.skip = Skip::None;
    Decision excluded;
    excluded.skip = Skip::Excluded;
    Decision off;
    off.skip = Skip::Disabled;
    const uint32_t on = kFlagEnabled | kFlagJavaFont;
    CHECK(javaHookGate(ok, on, 31, 2) == InstallSkip::None);
    CHECK(javaHookGate(ok, on, 36, 2) == InstallSkip::None);
    CHECK(javaHookGate(ok, on, 30, 2) == InstallSkip::ApiUnsupported);
    CHECK(javaHookGate(ok, on, 37, 2) == InstallSkip::None);
    CHECK(javaHookGate(ok, on, 38, 2) == InstallSkip::ApiUnsupported);
    CHECK(javaHookGate(ok, on | kFlagAllowNewerApi, 38, 2) == InstallSkip::None);
    CHECK(javaHookGate(ok, on | kFlagAllowNewerApi, 30, 2) == InstallSkip::ApiUnsupported);
    CHECK(javaHookGate(ok, kFlagEnabled, 34, 2) == InstallSkip::FeatureOff);
    CHECK(javaHookGate(ok, on, 34, 0) == InstallSkip::NoFaces);
    CHECK(javaHookGate(excluded, on, 34, 2) == InstallSkip::NotEligible);
    CHECK(javaHookGate(off, on, 34, 2) == InstallSkip::NotEligible);
    CHECK(std::strcmp(installSkipName(InstallSkip::None), "install") == 0);
}

struct Corpus {
    std::vector<unsigned char> regular, bold, latin, cjk, pua, mono, color, digits, ttc;
};

FaceSet faceSet(const Corpus &c) {
    FaceSet s;
    s.count = 2;
    s.specs[0].weight = 400;
    s.specs[1].weight = 700;
    s.faces[0] = MappedFace{&s.specs[0], c.regular.data(), c.regular.size()};
    s.faces[1] = MappedFace{&s.specs[1], c.bold.data(), c.bold.size()};
    return s;
}

ReplaceChoice run(const FaceSet &s, const std::vector<unsigned char> &font, int weight, bool italic,
                  const char *hint = nullptr, uint32_t ttc = 0) {
    ReplaceInput in;
    in.data = font.data();
    in.size = font.size();
    in.ttcIndex = ttc;
    in.nameHint = hint;
    in.weight = weight;
    in.italic = italic;
    return chooseReplacement(in, s);
}

void testReplace(const std::string &dir) {
    Corpus c;
    CHECK(readBytes(dir + "/cjk_body.ttf", &c.regular));
    CHECK(readBytes(dir + "/cjk_ext_f12.ttf", &c.bold));
    CHECK(readBytes(dir + "/latin_body.ttf", &c.latin));
    CHECK(readBytes(dir + "/cjk_only_f12.ttf", &c.cjk));
    CHECK(readBytes(dir + "/pua_ligature.ttf", &c.pua));
    CHECK(readBytes(dir + "/mono_post.ttf", &c.mono));
    CHECK(readBytes(dir + "/color_colr.ttf", &c.color));
    CHECK(readBytes(dir + "/digits_only.ttf", &c.digits));
    CHECK(readBytes(dir + "/pair.ttc", &c.ttc));
    if (g_failures) return;
    FaceSet s = faceSet(c);

    ReplaceChoice r = run(s, c.latin, 400, false);
    CHECK(r.outcome == Outcome::Replace && r.face == 0 && r.verdict == Verdict::ReplaceLatin);
    r = run(s, c.latin, 400, false);
    CHECK(r.outcome == Outcome::Replace && r.cacheHit);  // second build of the same font: cache
    r = run(s, c.cjk, 800, false);
    CHECK(r.outcome == Outcome::Replace && r.face == 1 && r.verdict == Verdict::ReplaceCjk);
    r = run(s, c.latin, 500, true);
    CHECK(r.outcome == Outcome::Replace && r.face == 0);  // 500 is nearer to 400 than 700
    r = run(s, c.latin, 400, false, "assets/fonts/fontawesome-webfont.ttf");
    CHECK(r.outcome == Outcome::Keep && r.reason == Reason::NameToken);
    CHECK(run(s, c.pua, 400, false).outcome == Outcome::Keep);
    CHECK(run(s, c.mono, 400, false).outcome == Outcome::Keep);
    CHECK(run(s, c.color, 400, false).outcome == Outcome::Keep);
    CHECK(run(s, c.digits, 400, false).outcome == Outcome::Keep);
    CHECK(run(s, c.ttc, 400, false, nullptr, 1).outcome == Outcome::Replace);
    CHECK(run(s, c.ttc, 400, false, nullptr, 2).outcome == Outcome::Keep);  // index out of range
    // A font built from one of our own faces (e.g. Font.Builder(font.getBuffer())) is left alone.
    CHECK(run(s, c.regular, 400, false).outcome == Outcome::AlreadyOurs);
    ReplaceInput inside;
    inside.data = c.bold.data() + 16;
    inside.size = 32;
    CHECK(chooseReplacement(inside, s).outcome == Outcome::AlreadyOurs);
    // Empty face set (never installed in that state) reports NoFace instead of guessing.
    FaceSet empty;
    clearVerdictCache();
    CHECK(run(empty, c.latin, 400, false).outcome == Outcome::NoFace);
    ReplaceInput none;
    CHECK(chooseReplacement(none, s).outcome == Outcome::Keep);
}

}  // namespace

int main(int argc, char **argv) {
    testGate();
    if (argc >= 2) testReplace(argv[1]);
    std::printf("java_policy_test: %s (%d failures)\n", g_failures ? "FAILED" : "passed", g_failures);
    return g_failures ? 1 : 0;
}
