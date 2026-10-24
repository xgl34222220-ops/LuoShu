// Config format, lookup and process decision tests; also drives the lsnf-config CLI end to end.
#include <cstring>
#include <string>

#include "config.h"
#include "test_util.h"

using namespace lsnf;

namespace {

const uint64_t kBoot = 0x1234;

std::vector<uint8_t> makeConfig(uint32_t flags, uint64_t boot = kBoot) {
    ConfigEntryIn in[] = {{"com.tencent.mm", kPkgExclude},
                          {"com.eg.android.AlipayGphone", kPkgExclude},
                          {"com.example.force", kPkgForce},
                          {"com.tencent.mm", kPkgForce},  // duplicate: bits merge
                          {"a.b", kPkgExclude}};
    std::vector<uint8_t> out(4096);
    size_t n = buildConfig(in, sizeof(in) / sizeof(in[0]), flags, boot, out.data(), out.size());
    CHECK(n > kConfigHeaderSize);
    out.resize(n);
    return out;
}

void testRoundTrip() {
    std::vector<uint8_t> blob = makeConfig(kFlagEnabled | kFlagVerbose);
    ConfigView v;
    CHECK(parseConfig(blob.data(), blob.size(), &v));
    CHECK(v.count == 4);
    CHECK(v.flags == (kFlagEnabled | kFlagVerbose));
    CHECK(lookupPackage(v, "com.tencent.mm", 14) == (kPkgExclude | kPkgForce));
    CHECK(lookupPackage(v, "com.eg.android.AlipayGphone", 27) == kPkgExclude);
    CHECK(lookupPackage(v, "a.b", 3) == kPkgExclude);
    CHECK(lookupPackage(v, "com.tencent", 11) == 0);
    CHECK(lookupPackage(v, "com.tencent.mmx", 15) == 0);
    CHECK(lookupPackage(v, "zzz", 3) == 0);
}

void testRejects() {
    std::vector<uint8_t> blob = makeConfig(kFlagEnabled);
    ConfigView v;
    for (size_t cut = 0; cut < blob.size(); ++cut) CHECK(!parseConfig(blob.data(), cut, &v));
    std::vector<uint8_t> bad = blob;
    bad[0] = 'X';
    CHECK(!parseConfig(bad.data(), bad.size(), &v));
    bad = blob;
    bad[4] = 2;  // version
    CHECK(!parseConfig(bad.data(), bad.size(), &v));
    bad = blob;
    bad[kConfigHeaderSize] = 0xFF;  // first name offset out of range
    CHECK(!parseConfig(bad.data(), bad.size(), &v));
    // Swap two entries -> unsorted -> rejected.
    bad = blob;
    uint8_t tmp[kConfigEntrySize];
    std::memcpy(tmp, &bad[kConfigHeaderSize], kConfigEntrySize);
    std::memcpy(&bad[kConfigHeaderSize], &bad[kConfigHeaderSize + kConfigEntrySize], kConfigEntrySize);
    std::memcpy(&bad[kConfigHeaderSize + kConfigEntrySize], tmp, kConfigEntrySize);
    CHECK(!parseConfig(bad.data(), bad.size(), &v));
    // Invalid package names are refused by the writer.
    ConfigEntryIn in[] = {{"com.bad name", kPkgExclude}};
    uint8_t out[256];
    CHECK(buildConfig(in, 1, 0, 0, out, sizeof(out)) == 0);
}

void testDecide() {
    std::vector<uint8_t> on = makeConfig(kFlagEnabled);
    std::vector<uint8_t> off = makeConfig(0);
    ConfigView von, voff;
    CHECK(parseConfig(on.data(), on.size(), &von));
    CHECK(parseConfig(off.data(), off.size(), &voff));
    ProcessInfo p;
    p.uid = 10123;
    p.niceName = "com.example.app";
    CHECK(decide(p, &von, kBoot).skip == Skip::None);
    CHECK(decide(p, &voff, kBoot).skip == Skip::Disabled);
    CHECK(decide(p, nullptr, kBoot).skip == Skip::NoConfig);
    CHECK(decide(p, &von, kBoot + 1).skip == Skip::StaleBoot);
    p.niceName = "com.tencent.mm:tools";
    CHECK(decide(p, &von, kBoot).skip == Skip::Excluded);
    p.niceName = "com.android.systemui";
    CHECK(decide(p, &von, kBoot).skip == Skip::HardExcluded);
    p.niceName = "com.example.app";
    p.uid = 1000;
    CHECK(decide(p, &von, kBoot).skip == Skip::SystemUid);
    p.uid = 1010123;  // secondary user, app id 10123
    CHECK(decide(p, &von, kBoot).skip == Skip::None);
    p.uid = 99000;
    CHECK(decide(p, &von, kBoot).skip == Skip::Isolated);
    p.uid = 10123;
    p.childZygote = true;
    CHECK(decide(p, &von, kBoot).skip == Skip::ChildZygote);
    p.childZygote = false;
    p.onDenylist = true;
    CHECK(decide(p, &von, kBoot).skip == Skip::Denylist);
    p.onDenylist = false;
    p.niceName = nullptr;
    CHECK(decide(p, &von, kBoot).skip == Skip::NoName);
    CHECK(packageLength("a.b:c") == 3);
    CHECK(bootHash("abc\n", 4) == bootHash(" abc", 4));
}

bool writeText(const std::string &path, const char *text) {
    FILE *f = std::fopen(path.c_str(), "wb");
    if (!f) return false;
    std::fputs(text, f);
    return std::fclose(f) == 0;
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

void testCli(const std::string &tool, const std::string &dir) {
    std::string boot = dir + "/boot_id.txt", ex = dir + "/exclude.list", force = dir + "/force.list",
                cfg = dir + "/cli_config.bin";
    CHECK(writeText(boot, "6f1c2c7e-0000-4000-8000-000000000001\n"));
    CHECK(writeText(ex, "# comment\ncom.tencent.mm\n  com.eg.android.AlipayGphone  # bank\n\ncom.tencent.mm\n"));
    CHECK(writeText(force, "com.example.force\n"));
    std::string build = tool + " build --out " + cfg + " --enabled 1 --verbose 0 --boot-id-file " + boot +
                        " --exclude " + ex + " --force " + force;
    CHECK(std::system(build.c_str()) == 0);
    CHECK(runCapture(tool + " lookup " + cfg + " com.tencent.mm") == "1\n");
    CHECK(runCapture(tool + " lookup " + cfg + " com.example.force") == "2\n");
    CHECK(runCapture(tool + " lookup " + cfg + " com.other") == "0\n");
    std::string dump = runCapture(tool + " dump " + cfg);
    CHECK(dump.find("enabled=1 verbose=0 java_font=0 count=3") != std::string::npos);
    // Feature switches are separate bits; the default build leaves them off.
    std::string jf = tool + " build --out " + cfg + ".jf --enabled 1 --java-font 1 --allow-newer-api 0 --boot-id-file " + boot;
    CHECK(std::system(jf.c_str()) == 0);
    CHECK(runCapture(tool + " dump " + cfg + ".jf").find("enabled=1 verbose=0 java_font=1 count=0") != std::string::npos);
    std::vector<unsigned char> blob;
    CHECK(readBytes(cfg, &blob));
    ConfigView v;
    CHECK(parseConfig(blob.data(), blob.size(), &v));
    const char *id = "6f1c2c7e-0000-4000-8000-000000000001";
    CHECK(v.bootHash == bootHash(id, std::strlen(id)));
    CHECK(writeText(ex, "com.bad name\n"));
    CHECK(std::system((build + " 2>/dev/null").c_str()) != 0);
}

}  // namespace

int main(int argc, char **argv) {
    testRoundTrip();
    testRejects();
    testDecide();
    if (argc >= 3) testCli(argv[1], argv[2]);
    std::printf("config_test: %s (%d failures)\n", g_failures ? "FAILED" : "passed", g_failures);
    return g_failures ? 1 : 0;
}
