#!/usr/bin/env python3
"""Byte protocol/security fixtures only; these bytes are not Android videos."""
from contextlib import ExitStack
import base64
import hashlib
import io
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dump_ui_original_media as media


EXPECTED = (
    ('light-cold-start.mp4', 'primary'),
    ('light-warm-start.mp4', 'primary'),
    ('dark-cold-start.mp4', 'primary'),
    ('dark-warm-start.mp4', 'primary'),
    ('diagnostic-only/diagnostic.mp4', 'diagnostic-only'),
)


def recover(text):
    """Independent strict consumer: completion, offsets, length, SHA and roles."""
    roles = {}
    records = {}
    current = None
    for line in text.splitlines():
        if line.startswith(('ERROR ', 'REJECTED ')):
            raise ValueError('rejected retention')
        if line.startswith('ROLE '):
            _, name, role = line.split()
            roles[name] = role.partition('=')[2]
        elif line.startswith('FILE '):
            if current is not None:
                raise ValueError('missing completion')
            match = re.fullmatch(r'FILE (\S+) bytes=(\d+) sha256=([0-9a-f]{64})', line)
            if match is None or match[1] in records:
                raise ValueError('invalid file')
            current = (match[1], int(match[2]), match[3], bytearray())
        elif line.startswith('BASE64 '):
            if current is None:
                raise ValueError('orphan chunk')
            match = re.fullmatch(r'BASE64 offset=(\d+) (\S+)', line)
            if match is None or int(match[1]) != len(current[3]) or len(match[2]) > 4096:
                raise ValueError('invalid offset or chunk')
            current[3].extend(base64.b64decode(match[2], validate=True))
        elif line.startswith('MEDIA_END '):
            match = re.fullmatch(r'MEDIA_END (\S+) role=(\S+) bytes=(\d+) sha256=([0-9a-f]{64})', line)
            if current is None or match is None:
                raise ValueError('orphan completion')
            name, size, digest, data = current
            if (match[1], match[2], int(match[3]), match[4]) != (name, roles.get(name), size, digest):
                raise ValueError('mismatched completion')
            if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
                raise ValueError('invalid bytes')
            records[name] = bytes(data)
            current = None
    if current is not None:
        raise ValueError('missing completion')
    return records


class OriginalMediaRetentionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.root = self.workspace / 'launch-visual-output'
        self.root.mkdir()

    def run_dump(self, output=None, workspace=None):
        output = io.StringIO() if output is None else output
        result = media.dump_original_media(self.workspace if workspace is None else workspace, output)
        return result, output.getvalue()

    def assert_boundary(self, text):
        lines = text.splitlines()
        match = re.fullmatch(r'::stop-commands::([0-9a-f]{32})', lines[0])
        self.assertIsNotNone(match)
        self.assertEqual('::' + match[1] + '::', lines[-1])
        return match[1]

    def test_original_binary_roundtrip_at_chunk_boundaries_and_empty_file(self):
        pattern = b'\x00\xff\x80binary\r\n::warning::fixture-command\n::add-mask::fixture-mask\n'
        for size in (0, 1, 2, 3071, 3072, 3073, 12289):
            with self.subTest(size=size):
                data = (pattern * (size // len(pattern) + 1))[:size]
                path = self.root / EXPECTED[0][0]
                path.write_bytes(data)
                result, text = self.run_dump()
                self.assertEqual(0, result)
                self.assert_boundary(text)
                self.assertEqual({EXPECTED[0][0]: data}, recover(text))
                self.assertEqual(data, path.read_bytes())
                self.assertNotIn('::warning::fixture-command', text)
                self.assertNotIn('::add-mask::fixture-mask', text)

    def test_exact_five_order_roles_and_missing_with_no_root(self):
        self.root.rmdir()
        result, text = self.run_dump()
        self.assertEqual(0, result)
        self.assert_boundary(text)
        self.assertEqual(['MISSING ' + name + ' role=' + role + ' reason=not-produced'
                          for name, role in EXPECTED], [line for line in text.splitlines() if line.startswith('MISSING ')])
        self.assertEqual({}, recover(text))

    def test_all_five_have_exact_roles_and_fixed_order_including_diagnostic(self):
        for i, (name, _) in enumerate(EXPECTED):
            path = self.root / name
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(bytes((i, 0xff, 0)))
        result, text = self.run_dump()
        self.assertEqual(0, result)
        self.assertEqual(['ROLE ' + name + ' role=' + role for name, role in EXPECTED],
                         [line for line in text.splitlines() if line.startswith('ROLE ')])
        self.assertEqual([name for name, _ in EXPECTED], list(recover(text)))
        self.assertIn('diagnostic-only is not primary acceptance', text)

    def test_missing_leaf_and_missing_diagnostic_parent_are_individual(self):
        result, text = self.run_dump()
        self.assertEqual(0, result)
        self.assertEqual(5, len([line for line in text.splitlines() if line.startswith('MISSING ')]))
        self.assertIn('MISSING diagnostic-only/diagnostic.mp4 role=diagnostic-only', text)

    def test_relative_traversal_or_filesystem_root_workspace_is_rejected_before_open(self):
        for workspace in (Path('relative'), self.workspace / '..', Path('/')):
            with self.subTest(workspace=workspace), patch.object(media.os, 'open', side_effect=AssertionError('must not open')):
                result, text = self.run_dump(workspace=workspace)
            self.assertEqual(1, result)
            self.assert_boundary(text)
            self.assertEqual(5, text.count('reason=invalid-workspace'))

    def test_workspace_symlink_component_is_rejected(self):
        actual = self.workspace / 'actual'
        actual.mkdir()
        (actual / 'nested').mkdir()
        linked = self.workspace / 'linked'
        linked.symlink_to(actual, target_is_directory=True)
        result, text = self.run_dump(workspace=linked / 'nested')
        self.assertEqual(1, result)
        self.assertEqual(5, text.count('REJECTED '))
        self.assertNotIn('FILE ', text)

    def test_root_symlink_and_non_directory_root_are_rejected(self):
        self.root.rmdir()
        actual = self.workspace / 'actual'
        actual.mkdir()
        for kind in ('symlink', 'regular'):
            with self.subTest(kind=kind):
                if kind == 'symlink': self.root.symlink_to(actual, target_is_directory=True)
                else: self.root.write_bytes(b'non-directory fixture')
                result, text = self.run_dump()
                self.assertEqual(1, result)
                self.assertEqual(5, text.count('REJECTED '))
                self.assertNotIn('BASE64 ', text)
                self.root.unlink()

    def test_diagnostic_parent_symlink_is_rejected_even_when_target_is_inside_root(self):
        actual = self.root / 'actual'
        actual.mkdir()
        (actual / 'diagnostic.mp4').write_bytes(b'decoy')
        (self.root / 'diagnostic-only').symlink_to(actual, target_is_directory=True)
        result, text = self.run_dump()
        self.assertEqual(1, result)
        self.assertIn('REJECTED diagnostic-only/diagnostic.mp4', text)
        self.assertNotIn('BASE64 ', text)

    def test_leaf_symlinks_inside_and_outside_root_are_rejected(self):
        outside = self.workspace / 'outside.bin'
        inside = self.root / 'inside.bin'
        outside.write_bytes(b'outside fixture')
        inside.write_bytes(b'inside fixture')
        target = self.root / EXPECTED[0][0]
        for source in (inside, outside):
            with self.subTest(source=source):
                target.symlink_to(source)
                result, text = self.run_dump()
                self.assertEqual(1, result)
                self.assertIn('REJECTED light-cold-start.mp4', text)
                self.assertNotIn('BASE64 ', text)
                target.unlink()

    def test_extra_hardlink_is_rejected_without_reading_content(self):
        outside = self.workspace / 'outside.bin'
        outside.write_bytes(b'outside fixture')
        os.link(outside, self.root / EXPECTED[0][0])
        with patch.object(media.os, 'read', side_effect=AssertionError('must not read')):
            result, text = self.run_dump()
        self.assertEqual(1, result)
        self.assertIn('reason=extra-hardlink', text)
        self.assertNotIn('BASE64 ', text)

    def test_nonregular_directory_and_fifo_are_rejected_without_blocking_or_reading(self):
        path = self.root / EXPECTED[0][0]
        for kind in ('directory', 'fifo'):
            with self.subTest(kind=kind):
                if kind == 'directory': path.mkdir()
                else: os.mkfifo(path)
                with patch.object(media.os, 'read', side_effect=AssertionError('must not read')):
                    result, text = self.run_dump()
                self.assertEqual(1, result)
                self.assertIn('reason=not-regular-file', text)
                if kind == 'directory': path.rmdir()
                else: path.unlink()

    def test_nonwhitelisted_relative_path_is_rejected_before_open(self):
        with ExitStack() as stack, patch.object(media.os, 'open', side_effect=AssertionError('must not open')):
            with self.assertRaisesRegex(media.MediaError, 'not-whitelisted'):
                media._media(-1, '../outside.bin', stack, [])

    def test_extra_decoy_files_are_not_opened_or_logged(self):
        for name in ('extra.mp4', 'unrelated.bin'):
            (self.root / name).write_bytes(b'decoy fixture')
        (self.root / 'nested').mkdir()
        (self.root / 'nested/other.mp4').write_bytes(b'decoy fixture')
        opened = []
        original = os.open
        def tracked(name, *args, **kwargs):
            opened.append(os.fspath(name))
            return original(name, *args, **kwargs)
        with patch.object(media.os, 'open', tracked):
            result, text = self.run_dump()
        self.assertEqual(0, result)
        self.assertFalse({'extra.mp4', 'unrelated.bin', 'nested', 'other.mp4'} & set(opened))
        self.assertNotIn('decoy', text)
        self.assertNotIn('FILE ', text)

    def test_output_failure_resumes_commands_and_continues_later_fixed_file(self):
        (self.root / EXPECTED[0][0]).write_bytes(b'first fixture')
        (self.root / EXPECTED[1][0]).write_bytes(b'second fixture')
        class FailOnce(io.StringIO):
            failed = False
            def write(self, value):
                if value.startswith('BASE64 ') and not self.failed:
                    self.failed = True
                    raise OSError('unprinted private error text')
                return super().write(value)
        result, text = self.run_dump(FailOnce())
        self.assertEqual(1, result)
        self.assert_boundary(text)
        self.assertIn('ERROR light-cold-start.mp4', text)
        self.assertIn('MEDIA_END light-warm-start.mp4', text)
        self.assertNotIn('unprinted private error text', text)
        with self.assertRaises(ValueError): recover(text)

    def test_partial_stop_command_failure_still_attempts_resume(self):
        class PartialStop(io.StringIO):
            command = None
            def write(self, value):
                if value.startswith('::stop-commands::') and self.command is None:
                    self.command = value
                    super().write(value[:10])
                    raise OSError('partial stop write')
                return super().write(value)
        output = PartialStop()
        with self.assertRaisesRegex(OSError, 'partial stop write'):
            self.run_dump(output)
        token = output.command.partition('::stop-commands::')[2]
        self.assertTrue(output.getvalue().endswith('::' + token + '::\n'))
        self.assertIn('\n::' + token + '::\n', output.getvalue())
        self.assertNotIn('FILE ', output.getvalue())

    def test_read_failure_is_error_not_missing_and_does_not_echo_exception(self):
        (self.root / EXPECTED[0][0]).write_bytes(b'fixture')
        with patch.object(media.os, 'read', side_effect=OSError('private fixture detail')):
            result, text = self.run_dump()
        self.assertEqual(1, result)
        self.assert_boundary(text)
        self.assertIn('ERROR light-cold-start.mp4', text)
        self.assertNotIn('private fixture detail', text)
        self.assertEqual(4, text.count('MISSING '))

    def test_path_replacement_during_stream_is_rejected_without_completion(self):
        path = self.root / EXPECTED[0][0]
        path.write_bytes(b'a' * 7000)
        replacement = self.root / 'replacement.bin'
        replacement.write_bytes(b'b' * 7000)
        class Replace(io.StringIO):
            changed = False
            def write(self, value):
                if value.startswith('BASE64 ') and not self.changed:
                    self.changed = True
                    os.replace(replacement, path)
                return super().write(value)
        result, text = self.run_dump(Replace())
        self.assertEqual(1, result)
        self.assertIn('reason=file-changed', text)
        self.assertNotIn('MEDIA_END light-cold-start.mp4', text)
        with self.assertRaises(ValueError): recover(text)

    def test_same_inode_change_during_stream_is_rejected_without_completion(self):
        path = self.root / EXPECTED[0][0]
        path.write_bytes(b'a' * 7000)
        class Modify(io.StringIO):
            changed = False
            def write(self, value):
                if value.startswith('BASE64 ') and not self.changed:
                    self.changed = True
                    with path.open('r+b') as stream:
                        stream.seek(4000)
                        stream.write(b'b')
                return super().write(value)
        result, text = self.run_dump(Modify())
        self.assertEqual(1, result)
        self.assertNotIn('MEDIA_END light-cold-start.mp4', text)
        with self.assertRaises(ValueError): recover(text)

    def test_root_replacement_during_stream_is_rejected(self):
        (self.root / EXPECTED[0][0]).write_bytes(b'a' * 7000)
        class ReplaceRoot(io.StringIO):
            changed = False
            def write(writer, value):
                if value.startswith('BASE64 ') and not writer.changed:
                    writer.changed = True
                    self.root.rename(self.workspace / 'old-output')
                    self.root.mkdir()
                return super().write(value)
        result, text = self.run_dump(ReplaceRoot())
        self.assertEqual(1, result)
        self.assertIn('reason=directory-changed', text)
        self.assertNotIn('MEDIA_END ', text)

    def test_workspace_replacement_while_root_is_missing_is_error_not_missing(self):
        workspace = self.workspace / 'nested'
        workspace.mkdir()
        original = os.open
        def changed(name, *args, **kwargs):
            if name == 'launch-visual-output':
                workspace.rename(self.workspace / 'old-nested')
                workspace.mkdir()
            return original(name, *args, **kwargs)
        with patch.object(media.os, 'open', changed):
            result, text = self.run_dump(workspace=workspace)
        self.assertEqual(1, result)
        self.assertIn('reason=directory-changed', text)
        self.assertNotIn('MISSING ', text)

    def test_diagnostic_parent_replacement_while_leaf_missing_is_error(self):
        parent = self.root / 'diagnostic-only'
        parent.mkdir()
        original = os.open
        def changed(name, *args, **kwargs):
            if name == 'diagnostic.mp4':
                parent.rename(self.root / 'old-diagnostic')
                parent.mkdir()
            return original(name, *args, **kwargs)
        with patch.object(media.os, 'open', changed):
            result, text = self.run_dump()
        self.assertEqual(1, result)
        self.assertIn('ERROR diagnostic-only/diagnostic.mp4 role=diagnostic-only reason=directory-changed', text)
        self.assertNotIn('MISSING diagnostic-only/diagnostic.mp4', text)

    def test_second_stream_digest_is_checked_even_if_metadata_is_unchanged(self):
        (self.root / EXPECTED[0][0]).write_bytes(b'a' * 7000)
        output = io.StringIO()
        original = os.read
        changed = []
        def corrupt(fd, size):
            data = original(fd, size)
            if data and 'FILE ' in output.getvalue() and not changed:
                changed.append(True)
                return b'b' + data[1:]
            return data
        with patch.object(media.os, 'read', corrupt):
            result, text = self.run_dump(output)
        self.assertEqual(1, result)
        self.assertEqual([True], changed)
        self.assertIn('reason=stream-mismatch', text)
        self.assertNotIn('MEDIA_END ', text)

    def test_strict_recovery_rejects_missing_completion_duplicate_offset_or_tampered_bytes(self):
        (self.root / EXPECTED[0][0]).write_bytes(b'a' * 4000)
        _, text = self.run_dump()
        chunk = next(line for line in text.splitlines() if line.startswith('BASE64 '))
        variants = (re.sub(r'^MEDIA_END .*\n', '', text, flags=re.MULTILINE),
                    text.replace(chunk, chunk + '\n' + chunk),
                    text.replace(chunk, 'BASE64 offset=0 ' + base64.b64encode(b'b' * 3072).decode('ascii')),
                    text.replace(chunk + '\n', ''),
                    text.replace(chunk, 'BASE64 offset=0 ***'),
                    text + 'ERROR light-cold-start.mp4 role=primary reason=file-changed\n')
        for variant in variants:
            with self.subTest(), self.assertRaises(ValueError): recover(variant)

    def test_command_boundary_is_unique_and_unexpected_cli_arguments_cannot_choose_files(self):
        _, first = self.run_dump()
        _, second = self.run_dump()
        self.assertNotEqual(self.assert_boundary(first), self.assert_boundary(second))
        output = io.StringIO()
        with patch.object(media, 'dump_original_media', wraps=media.dump_original_media) as dumped, \
                patch.object(media.sys, 'stdout', output), patch.object(media.os, 'open', side_effect=AssertionError('must not open')):
            self.assertEqual(1, media.main(['::warning::private-argument']))
        self.assertTrue(dumped.call_args.kwargs['reject_arguments'])
        self.assertNotIn('private-argument', output.getvalue())
        self.assert_boundary(output.getvalue())

    def test_cli_has_no_path_arguments_and_missing_output_is_explicit(self):
        self.root.rmdir()
        result = subprocess.run([sys.executable, str(Path(media.__file__).resolve())], cwd=self.workspace,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
        self.assertEqual(0, result.returncode)
        self.assertEqual(b'', result.stderr)
        text = result.stdout.decode('ascii')
        self.assert_boundary(text)
        self.assertEqual(5, text.count('MISSING '))

    def test_independent_always_step_and_check_registration_keep_original_launch_contract(self):
        root = Path(__file__).parent.parent
        workflow = (root / '.github/workflows/android-ui-smoke.yml').read_text()
        transport = workflow.index('      - name: Preserve complete snapshot transport diagnostics in job log')
        retention = workflow.index('      - name: Preserve original startup media bytes in job log')
        upload = workflow.index('      - name: Upload separate startup recordings and logs')
        self.assertLess(transport, retention)
        self.assertLess(retention, upload)
        self.assertIn('        if: always()\n', workflow[retention:upload])
        self.assertIn('python3 scripts/dump_ui_original_media.py\n', workflow[retention:upload])
        self.assertIn('--record-launch --visual-launch-only --snapshot-child-prefetch default --diagnostic-video-after-baseline-failure', workflow)
        self.assertIn('emulator-options: -no-window -gpu swiftshader -no-snapshot', workflow)
        self.assertIn('python3 "$ROOT/scripts/dump_ui_original_media_test.py"', (root / 'scripts/check.sh').read_text())


if __name__ == '__main__':
    unittest.main()
