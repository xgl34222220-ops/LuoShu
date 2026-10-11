#!/usr/bin/env python3
"""Bounded top-level JSON ``message`` reader for shell-captured tool output.

Android 15 bionic regexec can crash on the old greedy UTF-8 sed patterns, and
Android printf is an external executable that cannot receive an argument larger
than the kernel argv limit. Callers pass a file path, or ``-`` to stream an
already captured output through stdin. Only the last valid top-level string
``message`` is returned; nested look-alikes and cut-off records are ignored.
Exit status 1 means no message was found and the caller keeps its fallback.

Ported from LuoShu PR #264 (task_scope.py error-message / error-message-stdin).
"""
import json
import os
import sys
from pathlib import Path

ERROR_MESSAGE_READ_LIMIT = 256 * 1024


def error_message_from_file(path):
    """Read a bounded manager-output tail without Android libc regex calls.

    Managers emit standalone JSON records amongst human-readable log lines.
    Preserve the last valid top-level string message, never a nested lookalike
    or a malformed JSON fragment. The persisted task format is one key per line.
    """
    limit = ERROR_MESSAGE_READ_LIMIT
    try:
        if not Path(path).is_file():
            return ''
        with open(path, 'rb') as source:
            source.seek(0, os.SEEK_END)
            offset = max(0, source.tell() - limit)
            source.seek(offset)
            raw = source.read(limit)
        if offset:
            # The first bytes may be the middle of a log/UTF-8/JSON record.
            # Do not reinterpret a cut-off record as an independent response.
            raw = raw.partition(b'\n')[2]
        text = raw.decode('utf-8', errors='replace')
    except OSError:
        return ''

    return error_message_from_text(text)


def error_message_from_text(text):
    """Shared top-level JSON decoding for file tails and captured scanner pipes."""

    def extract(candidate):
        if not candidate.lstrip().startswith('{'):
            return ''
        try:
            value = json.loads(candidate)
        except (ValueError, RecursionError):
            return ''
        message = value.get('message') if isinstance(value, dict) else None
        if not isinstance(message, str):
            return ''
        # JSON escapes can include newlines, NULs or lone surrogates. Decode
        # correctly, then prevent them from injecting additional task fields.
        message = ''.join(' ' if ord(char) < 32 or char in '\x7f\x85\u2028\u2029' else char
                          for char in message[:4096]).strip()
        return message.encode('utf-8', errors='replace').decode('utf-8')

    # A complete pretty-printed response is valid too. Otherwise parse separate
    # log records in reverse; total examined input remains bounded above.
    complete = extract(text)
    if complete:
        return complete
    try:
        json.loads(text)
    except (ValueError, RecursionError):
        pass
    else:
        # A valid whole response without a top-level string message must not
        # accidentally expose a nested object while scanning individual lines.
        return ''
    for line in reversed(text.splitlines()):
        message = extract(line)
        if message:
            return message
    return ''


def error_message_stdin(_args):
    """Read a finite captured-output pipe with the same bounded tail semantics.

    This command is separate from the request owner's open stdin lease. Callers
    pipe an already completed scanner's captured text; no temporary file or new
    scope is created, and memory never grows with the entire scanner output.
    """
    raw = b''
    discarded = False
    try:
        while True:
            chunk = sys.stdin.buffer.read(64 * 1024)
            if not chunk:
                break
            raw += chunk
            if len(raw) > ERROR_MESSAGE_READ_LIMIT:
                raw = raw[-ERROR_MESSAGE_READ_LIMIT:]
                discarded = True
    except OSError:
        return 1
    if discarded:
        raw = raw.partition(b'\n')[2]
    message = error_message_from_text(raw.decode('utf-8', errors='replace'))
    if not message:
        return 1
    print(message)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print('usage: json_error_message.py FILE|-', file=sys.stderr)
        return 2
    if argv[0] == '-':
        return error_message_stdin(None)
    message = error_message_from_file(argv[0])
    if not message:
        return 1
    print(message)
    return 0


if __name__ == '__main__':
    sys.exit(main())
