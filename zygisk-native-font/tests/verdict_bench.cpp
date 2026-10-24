// Host micro benchmark for the verdict. Fails when an uncached verdict P95 exceeds 150 us or a
// cache hit averages above 1 us. Writes a one-line-per-font report to stdout.
#include <algorithm>
#include <chrono>
#include <fstream>
#include <sstream>

#include "sfnt_verdict.h"
#include "test_util.h"

using namespace lsnf;
using Clock = std::chrono::steady_clock;

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    std::string dir = argv[1];
    std::ifstream in(dir + "/expect.tsv");
    std::string line, last;
    double worstP95 = 0, worstHit = 0;
    std::printf("%-24s %10s %10s %10s\n", "font", "p50_us", "p95_us", "hit_us");
    while (std::getline(in, line)) {
        std::string file = line.substr(0, line.find('\t'));
        if (file == last) continue;
        last = file;
        std::vector<unsigned char> b;
        if (!readBytes(dir + "/" + file, &b)) continue;
        std::vector<double> samples;
        volatile int sink = 0;
        for (int i = 0; i < 400; ++i) {
            auto t0 = Clock::now();
            VerdictResult r = classify(b.data(), b.size(), 0, nullptr);
            auto t1 = Clock::now();
            sink += int(r.verdict);
            samples.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count());
        }
        std::sort(samples.begin(), samples.end());
        double p50 = samples[samples.size() / 2], p95 = samples[samples.size() * 95 / 100];
        clearVerdictCache();
        classifyCached(b.data(), b.size(), 0, nullptr);
        // Best of 5 batches: the minimum is the stable estimate of the hit cost on a shared runner.
        const int kHits = 20000;
        double hit = 1e9;
        for (int rep = 0; rep < 5; ++rep) {
            auto t0 = Clock::now();
            for (int i = 0; i < kHits; ++i) sink += int(classifyCached(b.data(), b.size(), 0, nullptr).verdict);
            hit = std::min(hit, std::chrono::duration<double, std::micro>(Clock::now() - t0).count() / kHits);
        }
        (void)sink;
        std::printf("%-24s %10.2f %10.2f %10.3f\n", file.c_str(), p50, p95, hit);
        worstP95 = std::max(worstP95, p95);
        worstHit = std::max(worstHit, hit);
    }
    std::printf("worst uncached p95 = %.2f us (limit 150), worst cache hit = %.3f us (limit 1)\n", worstP95, worstHit);
    CHECK(worstP95 > 0);
    CHECK(worstP95 < 150.0);
    CHECK(worstHit < 1.0);
    return g_failures ? 1 : 0;
}
