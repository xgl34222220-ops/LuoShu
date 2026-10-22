// SPDX-License-Identifier: GPL-3.0-only
// LuoShu WOFF2 decoder entry point.
//
// The embedded Android Python runtime ships FontTools as pure Python and has
// no Brotli extension, so WOFF2 import uses this small static executable. It
// links the pinned upstream google/woff2 decoder and the Brotli decoder (both
// MIT, see licenses/WOFF2-LICENSE.txt and licenses/Brotli-LICENSE.txt). It
// only turns one WOFF2 container into the SFNT it wraps; every result is still
// validated by LuoShu's own font checks afterwards.
//
// Usage: luoshu-woff2-decode INPUT.woff2 OUTPUT.ttf
// Exit codes: 0 ok, 2 usage, 3 read error, 4 decode error, 5 write error.

#include <cerrno>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include <woff2/decode.h>
#include <woff2/output.h>

namespace {

constexpr size_t kMaxInputBytes = 256u * 1024u * 1024u;
constexpr size_t kMaxOutputBytes = 512u * 1024u * 1024u;

bool ReadAll(const char* path, std::vector<uint8_t>* data) {
  FILE* file = std::fopen(path, "rb");
  if (file == nullptr) return false;
  uint8_t block[65536];
  bool ok = true;
  for (;;) {
    size_t n = std::fread(block, 1, sizeof(block), file);
    if (n > 0) {
      if (data->size() + n > kMaxInputBytes) { ok = false; break; }
      data->insert(data->end(), block, block + n);
    }
    if (n < sizeof(block)) {
      if (std::ferror(file)) ok = false;
      break;
    }
  }
  std::fclose(file);
  return ok;
}

bool WriteAll(const char* path, const std::string& data) {
  FILE* file = std::fopen(path, "wb");
  if (file == nullptr) return false;
  bool ok = std::fwrite(data.data(), 1, data.size(), file) == data.size();
  ok = (std::fflush(file) == 0) && ok;
  ok = (std::fclose(file) == 0) && ok;
  if (!ok) std::remove(path);
  return ok;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc != 3) {
    std::fprintf(stderr, "usage: luoshu-woff2-decode INPUT.woff2 OUTPUT.ttf\n");
    return 2;
  }
  std::vector<uint8_t> input;
  if (!ReadAll(argv[1], &input)) {
    std::fprintf(stderr, "cannot read input (%s)\n", errno ? std::strerror(errno) : "too large");
    return 3;
  }
  if (input.size() < 48 || std::memcmp(input.data(), "wOF2", 4) != 0) {
    std::fprintf(stderr, "input is not a WOFF2 file\n");
    return 4;
  }
  size_t expected = woff2::ComputeWOFF2FinalSize(input.data(), input.size());
  if (expected == 0 || expected > kMaxOutputBytes) {
    std::fprintf(stderr, "invalid WOFF2 header or decoded size\n");
    return 4;
  }
  std::string output;
  output.reserve(expected);
  woff2::WOFF2StringOut out(&output);
  out.SetMaxSize(kMaxOutputBytes);
  if (!woff2::ConvertWOFF2ToTTF(input.data(), input.size(), &out)) {
    std::fprintf(stderr, "WOFF2 decompression failed\n");
    return 4;
  }
  output.resize(out.Size());
  if (output.size() < 12 || !WriteAll(argv[2], output)) {
    std::fprintf(stderr, "cannot write output\n");
    return 5;
  }
  return 0;
}
