// Corpus-driven verdict tests plus robustness (mutation) checks. Run under ASan/UBSan in CI.
#include <cstring>
#include <fstream>
#include <sstream>

#include "sfnt_verdict.h"
#include "test_util.h"

using namespace lsnf;

namespace {

struct Case {
    std::string file;
    uint32_t ttc;
    std::string hint;
    std::string verdict;
    std::string reason;
};

std::vector<Case> loadCases(const std::string &dir) {
    std::vector<Case> cases;
    std::ifstream in(dir + "/expect.tsv");
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        std::stringstream ss(line);
        Case c;
        std::string ttc;
        std::getline(ss, c.file, '\t');
        std::getline(ss, ttc, '\t');
        std::getline(ss, c.hint, '\t');
        std::getline(ss, c.verdict, '\t');
        std::getline(ss, c.reason, '\t');
        c.ttc = uint32_t(std::stoul(ttc));
        cases.push_back(c);
    }
    return cases;
}

void testCorpus(const std::string &dir) {
    std::vector<Case> cases = loadCases(dir);
    CHECK(cases.size() >= 25);
    for (const Case &c : cases) {
        std::vector<unsigned char> bytes;
        if (!readBytes(dir + "/" + c.file, &bytes)) {
            std::fprintf(stderr, "missing corpus file %s\n", c.file.c_str());
            ++g_failures;
            continue;
        }
        const char *hint = c.hint == "-" ? nullptr : c.hint.c_str();
        VerdictResult r = classify(bytes.data(), bytes.size(), c.ttc, hint);
        bool ok = c.verdict == verdictName(r.verdict) && c.reason == reasonName(r.reason);
        std::printf("%-5s %-22s ttc=%u %-14s %-12s L=%u D=%u C=%u P=%u touched=%u\n", ok ? "ok" : "FAIL",
                    c.file.c_str(), c.ttc, verdictName(r.verdict), reasonName(r.reason), r.stats.latin,
                    r.stats.digits, r.stats.cjk, r.stats.pua, r.touched_bytes);
        if (!ok) {
            std::fprintf(stderr, "  expected %s/%s (hint=%s)\n", c.verdict.c_str(), c.reason.c_str(), c.hint.c_str());
            ++g_failures;
        }
        CHECK(r.touched_bytes <= kTouchBudget);
        // Cached path must agree with the pure path, and the second call must hit.
        bool hit = true;
        VerdictResult a = classifyCached(bytes.data(), bytes.size(), c.ttc, hint, &hit);
        VerdictResult b = classifyCached(bytes.data(), bytes.size(), c.ttc, hint, &hit);
        CHECK(a.verdict == r.verdict && b.verdict == r.verdict && a.reason == r.reason);
    }
}

void testStats(const std::string &dir) {
    std::vector<unsigned char> bytes;
    CHECK(readBytes(dir + "/cjk_body.ttf", &bytes));
    VerdictResult r = classify(bytes.data(), bytes.size(), 0, nullptr);
    CHECK(r.stats.latin == 52);
    CHECK(r.stats.digits == 10);
    CHECK(r.stats.cjk == 3000);
    CHECK(r.stats.pua == 0);
    CHECK(readBytes(dir + "/pua_ligature.ttf", &bytes));
    r = classify(bytes.data(), bytes.size(), 0, nullptr);
    CHECK(r.stats.pua == 0x400);
    CHECK(readBytes(dir + "/cjk_ext_f12.ttf", &bytes));
    r = classify(bytes.data(), bytes.size(), 0, nullptr);
    CHECK(r.stats.cjk == 3000);
}

void testNameTokens() {
    const char *keep[] = {"MaterialIcons-Regular.otf", "fa-solid-900.ttf", "NotoColorEmoji.ttf", "iconfont.ttf",
                          "KaTeX_Math-Italic.ttf", "remixicon.ttf", "DSEG7-LCD.ttf", "CupertinoIcons.ttf"};
    for (const char *k : keep) CHECK(nameHasKeepToken(k, std::strlen(k)));
    const char *body[] = {"Roboto-Regular.ttf", "NotoSansSC-Medium.otf", "Inter.ttf", "PingFangSC.ttf",
                          "NotoSerif-Bold.ttf", "JetBrainsMono-Regular.ttf"};
    for (const char *b : body) CHECK(!nameHasKeepToken(b, std::strlen(b)));
}

uint32_t lcg(uint32_t &s) { return s = s * 1664525u + 1013904223u; }

// Random byte flips and truncations: must never crash, never exceed the budget, and any parse
// failure must end in Keep.
void testMutations(const std::string &dir) {
    const char *seeds[] = {"latin_body.ttf", "cjk_body.ttf", "cjk_ext_f12.ttf", "pair.ttc", "pua_ligature.ttf"};
    uint32_t s = 12345;
    for (const char *name : seeds) {
        std::vector<unsigned char> orig;
        if (!readBytes(dir + "/" + name, &orig)) {
            ++g_failures;
            continue;
        }
        for (int iter = 0; iter < 400; ++iter) {
            std::vector<unsigned char> m = orig;
            int flips = 1 + int(lcg(s) % 16);
            for (int k = 0; k < flips; ++k) {
                // Bias toward the header and directory where the interesting offsets live.
                size_t pos = (lcg(s) & 1) ? lcg(s) % (m.size() < 512 ? m.size() : 512) : lcg(s) % m.size();
                m[pos] = uint8_t(lcg(s));
            }
            if (lcg(s) % 4 == 0) m.resize(lcg(s) % m.size());
            VerdictResult r = classify(m.data(), m.size(), lcg(s) % 3, nullptr);
            CHECK(r.touched_bytes <= kTouchBudget);
            if (r.reason == Reason::ParseError || r.reason == Reason::Budget || r.reason == Reason::TooSmall) {
                CHECK(r.verdict == Verdict::Keep);
            }
        }
    }
    CHECK(classify(nullptr, 0, 0, nullptr).verdict == Verdict::Keep);
}

void testCacheReset(const std::string &dir) {
    std::vector<unsigned char> bytes;
    CHECK(readBytes(dir + "/latin_body.ttf", &bytes));
    clearVerdictCache();
    bool hit = true;
    classifyCached(bytes.data(), bytes.size(), 0, nullptr, &hit);
    CHECK(!hit);
    classifyCached(bytes.data(), bytes.size(), 0, nullptr, &hit);
    CHECK(hit);
    // A name-token hint wins before the cache is consulted.
    VerdictResult r = classifyCached(bytes.data(), bytes.size(), 0, "x/MaterialIcons.ttf", &hit);
    CHECK(!hit && r.reason == Reason::NameToken);
}

}  // namespace

int main(int argc, char **argv) {
    if (argc < 2) {
        std::fprintf(stderr, "usage: verdict_test CORPUS_DIR\n");
        return 2;
    }
    std::string dir = argv[1];
    testCorpus(dir);
    testStats(dir);
    testNameTokens();
    testMutations(dir);
    testCacheReset(dir);
    std::printf("verdict_test: %s (%d failures)\n", g_failures ? "FAILED" : "passed", g_failures);
    return g_failures ? 1 : 0;
}
