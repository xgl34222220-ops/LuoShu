#!/bin/sh
# Shared assertions for the LuoShu shell test suite.
#
# Every module under common/ begins with `set +e`, so the moment a test sources one, the test's own
# `set -eu` is silently switched off and every bare assertion after that point becomes a no-op that
# can never fail the run. Restoring `set -e` is not an option either: module functions legitimately
# return non-zero (device_font_payload_build_install returns 2 on a cache miss, for example), so
# errexit would abort on correct behaviour. Assertions therefore have to fail loudly by themselves.
#
# Usage:
#   . "$ROOT/scripts/assert.sh"
#   CASE='policy/cache miss'          # optional label included in failure output
#   ok test -s "$file"                 # command must succeed
#   no test -e "$file"                 # command must fail
#   eq "$actual" "$expected"           # string equality
#   contains "$file" 'needle'          # file must contain a fixed string
CASE=${CASE:-'(unnamed)'}

fail() {
    printf 'FAIL [%s] %s: %s\n' "$CASE" "${0##*/}" "$*" >&2
    exit 1
}

ok() { "$@" || fail "expected success: $*"; }

no() { if "$@"; then fail "expected failure: $*"; fi; }

eq() { [ "$1" = "$2" ] || fail "expected '$2', got '$1'"; }

ne() { [ "$1" != "$2" ] || fail "expected something other than '$2'"; }

contains() { grep -Fq "$2" "$1" 2>/dev/null || fail "'$1' does not contain '$2'"; }

lacks() { grep -Fq "$2" "$1" 2>/dev/null && fail "'$1' unexpectedly contains '$2'" || true; }
