"""Read-only ANR evidence for the authorized .stabletest App on emulator-5554."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess

PACKAGE = 'io.github.xgl34222220.luoshu.stabletest'
MAX_TRACE_BYTES = 4 * 1024 * 1024
MAX_TRACE_FILES = 4
START = re.compile(r'^----- pid (\d+) at ([^\r\n]+) -----\r?$', re.MULTILINE)


def target_anr(text):
    """Match the ANR owner, not the target Activity metadata in another ANR."""
    owner = r'(?<![\w.])' + re.escape(PACKAGE) + r'(?![\w.])'
    for line in text.splitlines():
        if re.search(r'\bANR in ' + owner, line):
            return True
        if re.match(r'\s*Reason:', line) and re.search(owner, line):
            return True
    return False


def owned_trace_blocks(text):
    """Retain exact process blocks; never export another process's thread dump."""
    starts = list(START.finditer(text))
    blocks = []
    for index, start in enumerate(starts):
        stop = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        section = text[start.start():stop]
        command = re.search(r'^Cmd line: ([^\r\n]+)\r?$', section, re.MULTILINE)
        if command is None or command.group(1).strip() != PACKAGE:
            continue
        pid = start.group(1)
        end = re.search(r'^----- end ' + re.escape(pid) + r' -----\r?$', section, re.MULTILINE)
        # An unfinished target dump is diagnostic evidence, never proof of a
        # complete main-thread trace or a reason to accept a recovered App.
        raw = section[:end.end()] + '\n' if end else section
        blocks.append({'pid': int(pid), 'time': start.group(2),
                       'complete': end is not None, 'text': raw})
    return blocks


def capture_owned_anr(adb, magisk, output, label):
    """Bound reads under existing Magisk access; absence cannot green a gate."""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    summary = {'result': 'NOT_AVAILABLE', 'package': PACKAGE, 'files': [],
               'reads': [], 'errors': [], 'maximum_files': MAX_TRACE_FILES,
               'maximum_bytes_per_file': MAX_TRACE_BYTES,
               'scope': 'DIAGNOSTIC ONLY; exact target blocks, no acceptance substitute'}

    def read(query):
        result = subprocess.run(
            [adb, '-s', 'emulator-5554', 'shell', shlex.quote(magisk) + ' su -mm -c ' + shlex.quote(query)],
            capture_output=True, timeout=20,
        )
        # Whole trace output may contain other processes. Keep only byte/hash
        # metadata here; the saved text below contains exact target blocks.
        summary['reads'].append({'query': query, 'exit': result.returncode,
                                 'bytes': len(result.stdout),
                                 'sha256': hashlib.sha256(result.stdout).hexdigest()})
        if result.returncode:
            summary['errors'].append({'query': query, 'exit': result.returncode})
            return ''
        return result.stdout.decode('utf-8', errors='replace')

    try:
        paths = read('ls -1t /data/anr/anr_* 2>/dev/null').splitlines()
        paths = [p for p in paths if re.fullmatch(r'/data/anr/anr_[A-Za-z0-9_.:-]+', p)]
        for source in paths[:MAX_TRACE_FILES]:
            text = read('head -c ' + str(MAX_TRACE_BYTES) + ' ' + shlex.quote(source))
            for index, block in enumerate(owned_trace_blocks(text)):
                name = label + '-anr-' + Path(source).name + '-' + str(index) + '.txt'
                raw = block.pop('text').encode('utf-8')
                (output / name).write_bytes(raw)
                summary['files'].append(dict(block, source=source, file=name,
                                             bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                             source_read_at_limit=len(text.encode('utf-8')) >= MAX_TRACE_BYTES))
    except Exception as error:
        summary['errors'].append({'error': str(error)})
    if summary['files']:
        summary['result'] = 'CAPTURED'
    elif summary['errors']:
        summary['result'] = 'NOT_AVAILABLE_WITH_ERRORS'
    (output / (label + '-anr-summary.json')).write_text(json.dumps(summary, indent=2) + '\n')
    return summary
