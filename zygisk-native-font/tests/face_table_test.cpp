// Face table format, face-name parsing, style matching, fingerprint and mapping tests; drives the
// lsnf-config faces / dump-faces commands end to end.
#include <fcntl.h>
#include <unistd.h>

#include <cstring>
#include <string>

#include "config.h"
#include "face_table.h"
#include "test_util.h"

using namespace lsnf;

namespace {

FaceSpec spec(const char *name, uint16_t w, bool it, uint64_t size = 100, uint64_t fp = 7) {
    FaceSpec f;
    f.weight = w;
    f.italic = it;
    f.size = size;
    f.fingerprint = fp;
    std::strncpy(f.name, name, kFaceNameMax - 1);
    return f;
}

void testNames() {
    uint16_t w = 0;
    bool it = true;
    CHECK(parseFaceName("LuoShu-400.ttf", &w, &it) && w == 400 && !it);
    CHECK(parseFaceName("LuoShu-700i.ttf", &w, &it) && w == 700 && it);
    CHECK(parseFaceName("LuoShu-300Italic.otf", &w, &it) && w == 300 && it);
    CHECK(!parseFaceName("LuoShuMono-400.ttf", &w, &it));
    CHECK(!parseFaceName("LuoShu-040.ttf", &w, &it));
    CHECK(!parseFaceName("LuoShu-400.ttc", &w, &it));
    CHECK(!parseFaceName("LuoShuSlot-400.ttf", &w, &it));
    CHECK(!parseFaceName("Roboto-Regular.ttf", &w, &it));
    CHECK(!parseFaceName("LuoShu-400.ttf.bak", &w, &it));
    CHECK(!parseFaceName(nullptr, &w, &it));
}

void testPick() {
    FaceSpec up[] = {spec("LuoShu-300.ttf", 300, false), spec("LuoShu-400.ttf", 400, false),
                     spec("LuoShu-500.ttf", 500, false), spec("LuoShu-700.ttf", 700, false)};
    CHECK(pickFace(up, 4, 400, false) == 1);
    CHECK(pickFace(up, 4, 100, false) == 0);
    CHECK(pickFace(up, 4, 900, false) == 3);
    CHECK(pickFace(up, 4, 600, false) == 3);  // tie 500/700 above 400 -> heavier
    CHECK(pickFace(up, 4, 350, false) == 0);  // tie 300/400 at <=400 -> lighter
    CHECK(pickFace(up, 4, 450, false) == 2);  // tie 400/500 above 400 -> heavier
    CHECK(pickFace(up, 4, 700, true) == 3);   // no italic face -> nearest upright
    FaceSpec mixed[] = {spec("LuoShu-400.ttf", 400, false), spec("LuoShu-400i.ttf", 400, true),
                        spec("LuoShu-700.ttf", 700, false)};
    CHECK(pickFace(mixed, 3, 400, true) == 1);
    CHECK(pickFace(mixed, 3, 700, true) == 1);   // italic wins over weight
    CHECK(pickFace(mixed, 3, 700, false) == 2);
    CHECK(pickFace(mixed, 0, 400, false) == -1);
    CHECK(pickFace(nullptr, 3, 400, false) == -1);
}

void testFormat() {
    FaceSpec in[] = {spec("LuoShu-400.ttf", 400, false, 1234, 0xAABB), spec("LuoShu-700i.ttf", 700, true, 99, 1)};
    uint8_t buf[kFaceHeaderSize + kMaxFaces * kFaceEntrySize];
    size_t n = buildFaceTable(in, 2, 0x55, buf, sizeof(buf));
    CHECK(n == kFaceHeaderSize + 2 * kFaceEntrySize);
    FaceTable t;
    CHECK(parseFaceTable(buf, n, &t));
    CHECK(t.count == 2 && t.bootHash == 0x55);
    CHECK(t.faces[0].weight == 400 && !t.faces[0].italic && t.faces[0].size == 1234 && t.faces[0].fingerprint == 0xAABB);
    CHECK(std::strcmp(t.faces[1].name, "LuoShu-700i.ttf") == 0 && t.faces[1].italic);
    for (size_t cut = 0; cut < n; ++cut) CHECK(!parseFaceTable(buf, cut, &t));
    uint8_t bad[sizeof(buf)];
    std::memcpy(bad, buf, n);
    bad[0] = 'X';
    CHECK(!parseFaceTable(bad, n, &t));
    std::memcpy(bad, buf, n);
    bad[kFaceHeaderSize + 24] = '/';  // path separator in a name
    CHECK(!parseFaceTable(bad, n, &t));
    std::memcpy(bad, buf, n);
    bad[kFaceHeaderSize + 24 + 30] = 'x';  // garbage after the terminating NUL
    CHECK(!parseFaceTable(bad, n, &t));
    std::memcpy(bad, buf, n);
    bad[8] = 0;  // count 0
    CHECK(!parseFaceTable(bad, n, &t));
    FaceSpec badName[] = {spec("../evil.ttf", 400, false)};
    CHECK(buildFaceTable(badName, 1, 0, buf, sizeof(buf)) == 0);
    FaceSpec many[kMaxFaces + 1];
    for (auto &f : many) f = spec("LuoShu-400.ttf", 400, false);
    CHECK(buildFaceTable(many, kMaxFaces + 1, 0, buf, sizeof(buf)) == 0);
}

std::string writeFile(const std::string &path, size_t size, uint8_t seed) {
    std::vector<uint8_t> data(size);
    for (size_t i = 0; i < size; ++i) data[i] = uint8_t(seed + i * 31 + (i >> 9));
    FILE *f = std::fopen(path.c_str(), "wb");
    if (f) {
        std::fwrite(data.data(), 1, data.size(), f);
        std::fclose(f);
    }
    return path;
}

void testFingerprint() {
    std::vector<uint8_t> big(100000, 3), small(5000, 4);
    for (size_t i = 0; i < big.size(); ++i) big[i] = uint8_t(i * 7);
    std::vector<uint8_t> ht(2 * kFingerprintSpan);
    std::memcpy(ht.data(), big.data(), kFingerprintSpan);
    std::memcpy(ht.data() + kFingerprintSpan, big.data() + big.size() - kFingerprintSpan, kFingerprintSpan);
    CHECK(faceFingerprintSpans(ht.data(), big.size()) == faceFingerprint(big.data(), big.size()));
    uint64_t a = faceFingerprint(big.data(), big.size());
    big[10] ^= 1;
    CHECK(faceFingerprint(big.data(), big.size()) != a);
    big[10] ^= 1;
    big[big.size() - 3] ^= 1;
    CHECK(faceFingerprint(big.data(), big.size()) != a);
    CHECK(faceFingerprint(small.data(), small.size()) != faceFingerprint(small.data(), small.size() - 1));
}

std::string runCapture(const std::string &cmd) {
    std::string out;
    FILE *p = popen(cmd.c_str(), "r");
    if (!p) return out;
    char buf[256];
    while (std::fgets(buf, sizeof(buf), p)) out += buf;
    pclose(p);
    return out;
}

void testCliAndMap(const std::string &tool, const std::string &dir) {
    std::string fonts = dir + "/faces_fonts";
    std::system(("rm -rf " + fonts + " && mkdir -p " + fonts + "/primary " + fonts + "/payload").c_str());
    writeFile(fonts + "/payload/LuoShu-400.ttf", 70000, 1);   // > 2 spans: head/tail path
    writeFile(fonts + "/payload/LuoShu-700.ttf", 20000, 2);   // between 1 and 2 spans
    writeFile(fonts + "/payload/LuoShuMono-400.ttf", 3000, 3);
    std::string boot = dir + "/faces_boot.txt";
    FILE *b = std::fopen(boot.c_str(), "wb");
    std::fputs("11111111-2222-4333-8444-555555555555\n", b);
    std::fclose(b);
    std::string table = dir + "/faces.bin";
    std::string cmd = tool + " faces --out " + table + " --boot-id-file " + boot + " " + fonts +
                      "/payload/LuoShu-400.ttf " + fonts + "/payload/LuoShu-700.ttf " + fonts +
                      "/payload/LuoShuMono-400.ttf 2>/dev/null";
    CHECK(std::system(cmd.c_str()) == 0);
    std::string dump = runCapture(tool + " dump-faces " + table);
    CHECK(dump.find("faces=2") != std::string::npos);
    CHECK(dump.find("LuoShu-700.ttf\tweight=700\titalic=0") != std::string::npos);
    CHECK(dump.find("LuoShuMono") == std::string::npos);
    CHECK(std::system((tool + " faces --out " + table + ".none --boot-id-file " + boot + " " + fonts +
                       "/payload/LuoShuMono-400.ttf 2>/dev/null").c_str()) != 0);

    std::vector<unsigned char> blob;
    CHECK(readBytes(table, &blob));
    FaceTable t;
    CHECK(parseFaceTable(blob.data(), blob.size(), &t));
    const char *id = "11111111-2222-4333-8444-555555555555";
    CHECK(t.bootHash == bootHash(id, std::strlen(id)));

    // Primary dir empty -> both faces come from the fallback dir fd + relative path.
    int dfd = open(fonts.c_str(), O_RDONLY | O_DIRECTORY | O_CLOEXEC);
    CHECK(dfd >= 0);
    FaceSet set;
    CHECK(mapFaces(t, (fonts + "/primary").c_str(), dfd, "primary/../payload/", &set) == 2);
    CHECK(set.faces[0].size == 70000 && set.faces[0].spec == &set.specs[0]);
    CHECK(set.faces[0].addr && set.faces[0].addr[1] == uint8_t(1 + 31));
    unmapFaces(&set);
    CHECK(set.count == 0);
    // A changed file (same size, different bytes) is refused by the fingerprint check.
    writeFile(fonts + "/primary/LuoShu-400.ttf", 70000, 9);
    CHECK(mapFaces(t, (fonts + "/primary").c_str(), -1, nullptr, &set) == 0);
    // Correct copy in the primary dir is used without the fallback.
    writeFile(fonts + "/primary/LuoShu-400.ttf", 70000, 1);
    CHECK(mapFaces(t, (fonts + "/primary").c_str(), -1, nullptr, &set) == 1);
    CHECK(std::strcmp(set.specs[0].name, "LuoShu-400.ttf") == 0);
    unmapFaces(&set);
    close(dfd);
}

}  // namespace

int main(int argc, char **argv) {
    testNames();
    testPick();
    testFormat();
    testFingerprint();
    if (argc >= 3) testCliAndMap(argv[1], argv[2]);
    std::printf("face_table_test: %s (%d failures)\n", g_failures ? "FAILED" : "passed", g_failures);
    return g_failures ? 1 : 0;
}
