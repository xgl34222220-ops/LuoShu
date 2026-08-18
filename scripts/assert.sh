#!/system/bin/sh
# Shared strict assertions for shell regression tests.
# Usage: . "$(dirname "$0")/assert.sh"

assert_eq() {
  _expected="$1"
  _actual="$2"
  _message="${3:-values differ}"
  if [ "$_expected" != "$_actual" ]; then
    echo "ASSERT_EQ failed: $_message" >&2
    echo "  expected: $_expected" >&2
    echo "  actual:   $_actual" >&2
    return 1
  fi
}

assert_ne() {
  _unexpected="$1"
  _actual="$2"
  _message="${3:-values unexpectedly equal}"
  if [ "$_unexpected" = "$_actual" ]; then
    echo "ASSERT_NE failed: $_message" >&2
    echo "  value: $_actual" >&2
    return 1
  fi
}

assert_true() {
  _message="${1:-command failed}"
  shift
  if ! "$@"; then
    echo "ASSERT_TRUE failed: $_message" >&2
    return 1
  fi
}

assert_false() {
  _message="${1:-command unexpectedly succeeded}"
  shift
  if "$@"; then
    echo "ASSERT_FALSE failed: $_message" >&2
    return 1
  fi
}

assert_contains() {
  _haystack="$1"
  _needle="$2"
  _message="${3:-missing expected text}"
  case "$_haystack" in
    *"$_needle"*) ;;
    *)
      echo "ASSERT_CONTAINS failed: $_message" >&2
      echo "  needle: $_needle" >&2
      return 1
      ;;
  esac
}

assert_file_exists() {
  _path="$1"
  _message="${2:-expected file does not exist}"
  if [ ! -f "$_path" ]; then
    echo "ASSERT_FILE_EXISTS failed: $_message" >&2
    echo "  path: $_path" >&2
    return 1
  fi
}
