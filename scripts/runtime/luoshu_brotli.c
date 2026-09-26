/* SPDX-License-Identifier: GPL-3.0-only
 * Bounded decoder for the offline FontTools WOFF2 reader. Brotli remains MIT.
 * stdin is one complete Brotli stream; stdout is its decoded byte sequence.
 */
#include <brotli/decode.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/resource.h>

#define CHUNK 65536U
#define MAX_OUTPUT (256U * 1024U * 1024U)
#define MAX_INPUT (128U * 1024U * 1024U)

int main(void) {
    uint8_t input[CHUNK], output[CHUNK];
    size_t available_in = 0, input_total = 0, output_total = 0;
    const uint8_t *next_in = input;
    BrotliDecoderResult result = BROTLI_DECODER_RESULT_NEEDS_MORE_INPUT;
    struct rlimit cpu = {60, 60};
    struct rlimit memory = {512U * 1024U * 1024U, 512U * 1024U * 1024U};
    /* Parent also limits wall time; the subprocess never inherits unbounded work. */
    if (setrlimit(RLIMIT_CPU, &cpu) || setrlimit(RLIMIT_AS, &memory)) {
        fputs("cannot enforce decoder resource limits\n", stderr);
        return 2;
    }
    BrotliDecoderState *state = BrotliDecoderCreateInstance(NULL, NULL, NULL);
    if (!state) return 2;
    for (;;) {
        if (result == BROTLI_DECODER_RESULT_NEEDS_MORE_INPUT) {
            available_in = fread(input, 1, CHUNK, stdin);
            input_total += available_in;
            next_in = input;
            if (!available_in || input_total > MAX_INPUT) break;
        }
        size_t available_out = CHUNK;
        uint8_t *next_out = output;
        result = BrotliDecoderDecompressStream(state, &available_in, &next_in,
                                               &available_out, &next_out, NULL);
        size_t produced = CHUNK - available_out;
        output_total += produced;
        if (output_total > MAX_OUTPUT) break;
        if (produced && fwrite(output, 1, produced, stdout) != produced) break;
        if (result == BROTLI_DECODER_RESULT_SUCCESS) {
            /* Reject trailing input and truncation instead of importing a prefix. */
            int trailing = fgetc(stdin);
            int valid = !available_in && trailing == EOF && !ferror(stdin);
            BrotliDecoderDestroyInstance(state);
            return valid && fflush(stdout) == 0 ? 0 : 1;
        }
        if (result == BROTLI_DECODER_RESULT_ERROR) break;
    }
    BrotliDecoderDestroyInstance(state);
    fputs("invalid, truncated, or oversized Brotli stream\n", stderr);
    return 1;
}
