#!/usr/bin/env python3
"""One public UiAutomation connection for a real CI snapshot run.

The protocol lives only in the debuggable test helper's private files. Every
response is bound to this session and request; no previous XML is a fallback.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
import threading
import time
import uuid
from collections import deque
from pathlib import Path


HELPER = "io.github.xgl34222220.luoshu.uisnapshot"
PROTOCOL = 1
ROOT_WAIT_MS = 8000
PUBLICATION_KEY = b"luoshu_snapshot_published"
PUBLICATION_LIMIT = 512
TIMING_RECORD_LIMIT = 128


class UiSnapshotSession:
    def __init__(self, adb_command: list[str], output: Path, *, child_prefetch_mode: str = "zero",
                 expected_api_level: int | None = None):
        if type(child_prefetch_mode) is not str or child_prefetch_mode not in ("zero", "default"):
            raise ValueError("Invalid child prefetch mode")
        if expected_api_level is not None and (type(expected_api_level) is not int or expected_api_level <= 0):
            raise ValueError("Invalid expected snapshot SDK")
        self.adb_command = adb_command
        self.output = output
        self.child_prefetch_mode = child_prefetch_mode
        self.expected_api_level = expected_api_level
        self.actual_api_level: int | None = None
        self.nonce = uuid.uuid4().hex
        self.directory = f"files/ui-snapshot-session-{self.nonce}"
        self.process = None
        self.started = False
        self.ready = False
        self._begin_started_monotonic: float | None = None
        self._first_capture_deadline: float | None = None
        self.closed = False
        self.fatal_error: str | None = None
        self.filenames: set[str] = set()
        self.events: list[dict[str, object]] = []
        self.commands: list[dict[str, object]] = []
        self.diagnostic_errors: list[str] = []
        self._pipe_condition = threading.Condition()
        self._pipe_bytes = {"stdout": bytearray(), "stderr": bytearray()}
        self._pipe_eof: set[str] = set()
        self._pipe_error: str | None = None
        self._pipe_threads: list[threading.Thread] = []
        self._publications: deque[str] = deque()
        self._published_names: set[str] = set()
        self._launch_timing: dict[str, object] = {}
        self._first_pipe_chunk: dict[str, float] = {}
        self._notice_timings: deque[dict[str, object]] = deque(maxlen=TIMING_RECORD_LIMIT)
        self._pending_notice_timings: dict[str, dict[str, object]] = {}
        self._notice_count = 0
        self._json_timings: deque[dict[str, object]] = deque(maxlen=TIMING_RECORD_LIMIT)
        self._json_count = 0
        self._ready_notice_timing: dict[str, object] | None = None
        self._ready_json_timing: dict[str, object] | None = None

    def _publication_frame(self, values: list[tuple[bytes, bytes]], code: bytes) -> None:
        notices = [value for key, value in values if key == PUBLICATION_KEY]
        if not notices:
            return
        if code != b"1" or len(values) != 1 or len(notices) != 1:
            raise RuntimeError("UiAutomation session publication frame is malformed")
        raw = notices[0]
        if len(raw) > PUBLICATION_LIMIT:
            raise RuntimeError("UiAutomation session publication notice is too large")

        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("duplicate publication key")
                result[key] = value
            return result

        try:
            notice = json.loads(raw, object_pairs_hook=unique_pairs)
        except (ValueError, UnicodeDecodeError) as error:
            raise RuntimeError("UiAutomation session publication notice is malformed") from error
        if not isinstance(notice, dict) or set(notice) != {"protocol", "nonce", "basename"}:
            raise RuntimeError("UiAutomation session publication notice fields mismatch")
        self._validate(notice)
        basename = notice["basename"]
        if type(basename) is not str or not re.fullmatch(r"ready\.json|response-[0-9a-f]{32}\.json", basename):
            raise RuntimeError("UiAutomation session publication basename mismatch")
        if basename in self._published_names:
            raise RuntimeError("UiAutomation session duplicate publication notice")
        if len(self._publications) >= 2:
            raise RuntimeError("UiAutomation session unexpected publication backlog")
        self._published_names.add(basename)
        self._publications.append(basename)
        # This is when the reader has parsed a complete, valid status frame,
        # not the native sendStatus return or an estimated remote arrival.
        timing: dict[str, object] = {"basename": basename,
                                   "status_frame_observed_monotonic_seconds": time.monotonic()}
        self._notice_count += 1
        self._notice_timings.append(timing)
        self._pending_notice_timings[basename] = timing
        if basename == "ready.json":
            self._ready_notice_timing = timing

    def _read_pipe(self, stream: str) -> None:
        pending = bytearray()
        values: list[tuple[bytes, bytes]] = []
        discard_line = False
        parser_failed = False
        pipe = None
        try:
            pipe = getattr(self.process, stream)
            while True:
                chunk = pipe.read1(4096)
                chunk_observed = time.monotonic()
                with self._pipe_condition:
                    if not chunk:
                        if stream == "stdout" and not parser_failed and (values or pending.startswith(
                                (b"INSTRUMENTATION_STATUS:", b"INSTRUMENTATION_STATUS_CODE:"))):
                            self._pipe_error = self._pipe_error or "UiAutomation session publication stream ended mid-record"
                        self._pipe_eof.add(stream)
                        self._pipe_condition.notify_all()
                        return
                    self._pipe_bytes[stream].extend(chunk)
                    if stream not in self._first_pipe_chunk:
                        self._first_pipe_chunk[stream] = chunk_observed
                    if stream == "stdout" and not parser_failed:
                        try:
                            if discard_line:
                                _, separator, chunk = chunk.partition(b"\n")
                                if not separator:
                                    continue
                                discard_line = False
                            pending.extend(chunk)
                            while b"\n" in pending:
                                line, _, rest = pending.partition(b"\n")
                                pending = bytearray(rest)
                                if line.startswith((b"INSTRUMENTATION_STATUS:", b"INSTRUMENTATION_STATUS_CODE:")) and len(line) > 4096:
                                    raise RuntimeError("UiAutomation session status line is too large")
                                if line.startswith(b"INSTRUMENTATION_STATUS: "):
                                    key, separator, value = line[len(b"INSTRUMENTATION_STATUS: "):].partition(b"=")
                                    if not separator or len(values) >= 16:
                                        raise RuntimeError("UiAutomation session status frame is malformed")
                                    values.append((key, value))
                                elif line.startswith(b"INSTRUMENTATION_STATUS_CODE: "):
                                    self._publication_frame(values, line[len(b"INSTRUMENTATION_STATUS_CODE: "):])
                                    values = []
                                elif any(key == PUBLICATION_KEY for key, _ in values):
                                    raise RuntimeError("UiAutomation session publication frame was interrupted")
                            if len(pending) > 4096:
                                if any(key == PUBLICATION_KEY for key, _ in values):
                                    raise RuntimeError("UiAutomation session publication frame was interrupted")
                                if pending.startswith((b"INSTRUMENTATION_STATUS:", b"INSTRUMENTATION_STATUS_CODE:")):
                                    raise RuntimeError("UiAutomation session status line is too large")
                                pending.clear()
                                discard_line = True
                        except Exception as error:
                            # Protocol failure remains fatal, but raw stdout
                            # must keep draining through the final result/EOF.
                            self._pipe_error = self._pipe_error or str(error)
                            parser_failed = True
                            pending.clear()
                            values.clear()
                    self._pipe_condition.notify_all()
        except Exception as error:
            with self._pipe_condition:
                self._pipe_error = self._pipe_error or str(error)
                self._pipe_eof.add(stream)
                self._pipe_condition.notify_all()
        finally:
            if pipe is not None:
                pipe.close()

    def _start_readers(self) -> None:
        for stream in ("stdout", "stderr"):
            thread = threading.Thread(target=self._read_pipe, args=(stream,), daemon=True)
            self._pipe_threads.append(thread)
            thread.start()

    def _wait_publication(self, basename: str, deadline: float) -> dict[str, object]:
        with self._pipe_condition:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError(f"UiAutomation session timed out waiting for {basename}")
                if self._pipe_error:
                    raise RuntimeError(self._pipe_error)
                if self.process.poll() is not None or "stdout" in self._pipe_eof:
                    raise RuntimeError("UiAutomation session exited before its matching response")
                if self._publications:
                    if self._publications.popleft() != basename:
                        raise RuntimeError("UiAutomation session publication basename mismatch")
                    timing = self._pending_notice_timings.pop(basename)
                    timing["consumed_monotonic_seconds"] = time.monotonic()
                    return timing.copy()
                self._pipe_condition.wait(min(.1, remaining))

    def _finish_readers(self, deadline: float) -> tuple[bytes, bytes]:
        self.process.wait(timeout=max(0, deadline - time.monotonic()))
        with self._pipe_condition:
            while len(self._pipe_eof) != 2:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired(self.process.args, 0)
                self._pipe_condition.wait(min(.1, remaining))
            stdout, stderr = bytes(self._pipe_bytes["stdout"]), bytes(self._pipe_bytes["stderr"])
        for thread in self._pipe_threads:
            thread.join(timeout=max(0, deadline - time.monotonic()))
            if thread.is_alive():
                raise subprocess.TimeoutExpired(self.process.args, 0)
        return stdout, stderr

    def _instrumentation_evidence(self, stdout: bytes, stderr: bytes) -> None:
        self._diagnostic_write(self.output / "ui-snapshot-session-instrumentation-stdout.bin", stdout)
        self._diagnostic_write(self.output / "ui-snapshot-session-instrumentation-stderr.bin", stderr)
        (self.output / "ui-snapshot-session-instrumentation.txt").write_bytes(stdout + stderr)

    def _check_pipe_error(self) -> None:
        with self._pipe_condition:
            if self._pipe_error:
                raise RuntimeError(self._pipe_error)

    def _diagnostic_write(self, path: Path, content: bytes) -> None:
        try:
            path.write_bytes(content)
        except Exception as error:
            # Evidence cannot replace a command's real result or primary error.
            self.diagnostic_errors.append(f"{path.name}: {type(error).__name__}: {error}")

    def _event(self, event: str, **details: object) -> None:
        self.events.append({"event": event, "monotonic_seconds": time.monotonic(), **details})
        # The reader never performs disk I/O or an extra RPC for timing. Copy
        # under its existing lock and persist with this existing event write.
        with self._pipe_condition:
            timing = {"clock": "host time.monotonic only; not native uptime",
                      "first_pipe_chunk_scope": "read1 returned bytes to the owned reader; not remote arrival",
                      "status_frame_observed_scope": "complete valid frame parsed by stdout reader",
                      "json_read_attempt_scope": "includes notice wait; actual cat execution is in ui-snapshot-commands.json",
                      "launch": self._launch_timing.copy(),
                      "first_pipe_chunk_monotonic_seconds": self._first_pipe_chunk.copy(),
                      "ready_notice": self._ready_notice_timing.copy() if self._ready_notice_timing else None,
                      "ready_json_read_attempt": self._ready_json_timing.copy() if self._ready_json_timing else None,
                      "publication_count": self._notice_count,
                      "publication_records_omitted": max(0, self._notice_count - len(self._notice_timings)),
                      "publications": [record.copy() for record in self._notice_timings],
                      "json_read_attempt_count": self._json_count,
                      "json_read_attempt_records_omitted": max(0, self._json_count - len(self._json_timings)),
                      "json_read_attempts": [record.copy() for record in self._json_timings]}
        self._diagnostic_write(self.output / "ui-snapshot-session.json", (json.dumps(
            {"protocol": PROTOCOL, "nonce": self.nonce, "events": self.events,
             "child_prefetch_mode": self.child_prefetch_mode, "expected_sdk_api": self.expected_api_level,
             "actual_sdk_api": self.actual_api_level,
             "diagnostic_errors": self.diagnostic_errors, "host_transport_timing": timing},
            ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def _record_command(self, record: dict[str, object], stdout: bytes, stderr: bytes) -> None:
        index = len(self.commands) + 1
        prefix = f"ui-snapshot-command-{self.nonce}-{index:04d}"
        record.update({"index": index, "stdout": prefix + "-stdout.bin",
                       "stderr": prefix + "-stderr.bin", "stdout_bytes": len(stdout),
                       "stderr_bytes": len(stderr)})
        self.commands.append(record)
        self._diagnostic_write(self.output / str(record["stdout"]), stdout)
        self._diagnostic_write(self.output / str(record["stderr"]), stderr)
        self._diagnostic_write(self.output / "ui-snapshot-commands.json", (json.dumps(
            {"protocol": PROTOCOL, "nonce": self.nonce, "commands": self.commands,
             "diagnostic_errors": self.diagnostic_errors},
            ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    def _run(self, arguments: list[str], *, timeout: float, payload: bytes | None = None):
        command = self.adb_command + arguments
        record: dict[str, object] = {"arguments": command, "timeout_seconds": timeout,
                                    "started_unix_seconds": time.time()}
        stdout = stderr = b""
        started = time.monotonic()
        record["started_monotonic_seconds"] = started
        try:
            result = subprocess.run(command, input=payload, capture_output=True, timeout=timeout)
            ended = time.monotonic()
            record.update({"outcome": "returned", "returncode": result.returncode})
            stdout, stderr = result.stdout, result.stderr
            return result
        except subprocess.TimeoutExpired as error:
            ended = time.monotonic()
            record.update({"outcome": "timeout", "returncode": None})
            stdout, stderr = error.stdout or b"", error.stderr or b""
            raise RuntimeError("UiAutomation session adb command timed out") from error
        except OSError as error:
            ended = time.monotonic()
            record.update({"outcome": "os-error", "returncode": None,
                           "error": f"{type(error).__name__}: {error}"})
            raise
        finally:
            if "outcome" not in record:
                ended = time.monotonic()
                record.update({"outcome": "interrupted", "returncode": None})
            # No diagnostic I/O precedes the actual command. These writes still
            # consume the caller's existing deadline; no timeout is restarted.
            record.update({"ended_monotonic_seconds": ended,
                           "elapsed_seconds": ended - started,
                           "ended_unix_seconds": time.time()})
            try:
                self._record_command(record, stdout, stderr)
            except Exception as error:
                self.diagnostic_errors.append(f"command evidence: {type(error).__name__}: {error}")

    def _write(self, basename: str, envelope: dict[str, object], *, timeout: float) -> None:
        path = f"{self.directory}/{basename}"
        # Only generated/validated basenames enter the remote shell command.
        command = f"cat > {path}.tmp && mv {path}.tmp {path}"
        result = self._run(["shell", "-T", "run-as", HELPER, "sh", "-c", shlex.quote(command)],
                           timeout=timeout, payload=json.dumps(envelope).encode("utf-8"))
        if result.returncode:
            raise RuntimeError("Cannot write UiAutomation session request: " +
                               (result.stdout + result.stderr).decode("utf-8", "replace"))

    def _wait_json(self, basename: str, evidence: Path, deadline: float) -> dict[str, object]:
        timing: dict[str, object] = {"basename": basename, "deadline_monotonic_seconds": deadline,
                                   "started_monotonic_seconds": time.monotonic(), "outcome": "waiting-notice"}
        self._json_count += 1
        self._json_timings.append(timing)
        if basename == "ready.json":
            self._ready_json_timing = timing
        try:
            receipt = self._wait_publication(basename, deadline)
            timing["notice_consumed_monotonic_seconds"] = time.monotonic()
            timing["notice_receipt"] = receipt
            timing["outcome"] = "notice-consumed"
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"UiAutomation session timed out waiting for {basename}")
            timing["cat_started_monotonic_seconds"] = time.monotonic()
            timing["cat_command_index"] = len(self.commands) + 1
            try:
                result = self._run(["shell", "run-as", HELPER, "cat", f"{self.directory}/{basename}"], timeout=remaining)
            finally:
                timing["cat_finished_monotonic_seconds_including_host_command_evidence"] = time.monotonic()
            if result.returncode:
                raise RuntimeError("UiAutomation session published JSON is unavailable")
            evidence.write_bytes(result.stdout)
            timing["json_evidence_written_monotonic_seconds"] = time.monotonic()
            if time.monotonic() >= deadline:
                raise RuntimeError(f"UiAutomation session timed out while reading {basename}")
            if self.process.poll() is not None:
                raise RuntimeError("UiAutomation session exited before its matching response")
            self._check_pipe_error()
            try:
                value = json.loads(result.stdout)
            except (ValueError, UnicodeDecodeError) as error:
                raise RuntimeError("UiAutomation session returned malformed JSON") from error
            if not isinstance(value, dict):
                raise RuntimeError("UiAutomation session response is not an object")
            timing["outcome"] = "json-decoded"
            return value
        except Exception as error:
            timing.update({"outcome": "failed", "error": f"{type(error).__name__}: {error}"})
            raise
        finally:
            timing["finished_monotonic_seconds"] = time.monotonic()

    def _validate(self, envelope: dict[str, object], **expected: object) -> None:
        if not isinstance(envelope, dict):
            raise RuntimeError("UiAutomation session response is not an object")
        for key, value in {"protocol": PROTOCOL, "nonce": self.nonce, **expected}.items():
            if type(envelope.get(key)) is not type(value) or envelope.get(key) != value:
                raise RuntimeError(f"UiAutomation session response mismatch for {key}")

    def _validate_child_prefetch(self, envelope: dict[str, object]) -> None:
        sdk = envelope.get("sdk_api")
        if type(sdk) is not int or sdk <= 0:
            raise RuntimeError("UiAutomation session response mismatch for sdk_api")
        if ((self.expected_api_level is not None and sdk != self.expected_api_level) or
                (self.actual_api_level is not None and sdk != self.actual_api_level)):
            raise RuntimeError("UiAutomation session response mismatch for sdk_api")
        strategy = ("legacy-platform-default" if sdk < 33 else
                    "api33-zero-prefetch" if self.child_prefetch_mode == "zero" else "api33-platform-default")
        self._validate(envelope, child_prefetch_mode=self.child_prefetch_mode, child_query_strategy=strategy)
        self.actual_api_level = sdk

    def begin(self, deadline: float) -> None:
        """Launch the owned connection/readers; leave ready validation to start."""
        if self.closed or self.fatal_error:
            raise RuntimeError(self.fatal_error or "UiAutomation session is closed")
        if self.started:
            return
        self.started = True  # A broken connection is never silently restarted.
        started = time.monotonic()
        self._begin_started_monotonic = started
        self._first_capture_deadline = min(started + 20, deadline)
        self._launch_timing["first_capture_deadline_monotonic_seconds"] = self._first_capture_deadline
        try:
            if started >= self._first_capture_deadline:
                raise RuntimeError("UiAutomation session timed out before starting its connection")
            self._launch_timing["popen_started_monotonic_seconds"] = time.monotonic()
            try:
                self.process = subprocess.Popen(self.adb_command + ["shell", "am", "instrument", "-w", "-r",
                    "-e", "session_nonce", self.nonce, "-e", "child_prefetch_mode", self.child_prefetch_mode,
                    f"{HELPER}/.SnapshotInstrumentation"],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            finally:
                self._launch_timing["popen_returned_monotonic_seconds"] = time.monotonic()
            if type(self.process.pid) is int:
                self._launch_timing["host_adb_pid"] = self.process.pid
            self._launch_timing["readers_starting_monotonic_seconds"] = time.monotonic()
            self._start_readers()
            self._launch_timing["readers_started_monotonic_seconds"] = time.monotonic()
            self._event("started")
            if time.monotonic() >= self._first_capture_deadline:
                raise RuntimeError("UiAutomation session timed out while starting its connection")
        except (OSError, RuntimeError, ValueError) as error:
            self.fatal_error = str(error)
            self._event("start-failed", error=str(error))
            raise

    def start(self, deadline: float) -> None:
        self.begin(deadline)
        if self.ready:
            return
        # begin may run during the caller's initial probes. Neither waiting for
        # ready nor the first later capture can restart its original ceiling.
        deadline = min(deadline, self._first_capture_deadline)
        try:
            ready = self._wait_json("ready.json", self.output / "ui-snapshot-session-ready.json", deadline)
            self._validate(ready, state="ready", root_wait_ms=ROOT_WAIT_MS)
            self._validate_child_prefetch(ready)
            self.ready = True
            self._event("ready", root_wait_ms=ROOT_WAIT_MS,
                        elapsed_seconds=time.monotonic() - self._begin_started_monotonic)
        except (OSError, RuntimeError, ValueError) as error:
            self.fatal_error = str(error)
            self._event("start-failed", error=str(error))
            raise

    def capture(self, filename: str, *, deadline: float | None = None) -> tuple[dict[str, str], str | None]:
        if not re.fullmatch(r"hierarchy-[0-9]{4,8}\.xml", filename):
            raise ValueError("Invalid real snapshot filename")
        if filename in self.filenames:
            raise RuntimeError("UiAutomation session filename cannot be reused")
        if self.closed or self.fatal_error:
            raise RuntimeError(self.fatal_error or "UiAutomation session is closed")
        first_capture = not self.filenames
        self.filenames.add(filename)
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        # A caller may share its original absolute deadline with this read.
        # The normal twenty-second host ceiling and server root wait stay fixed.
        deadline = min(started + 20, deadline) if deadline is not None else started + 20
        if first_capture and self._first_capture_deadline is not None:
            deadline = min(deadline, self._first_capture_deadline)
        envelope = {"protocol": PROTOCOL, "nonce": self.nonce, "request_id": request_id,
                    "filename": filename, "root_wait_ms": ROOT_WAIT_MS}
        prefix = self.output / filename.removesuffix(".xml")
        prefix.with_name(prefix.name + "-session-request.json").write_text(
            json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
        try:
            if time.monotonic() >= deadline:
                raise RuntimeError("UiAutomation session timed out before starting its capture")
            self.start(deadline)
            if time.monotonic() >= deadline:
                raise RuntimeError("UiAutomation session timed out before publishing its request")
            self._write(f"request-{request_id}.json", envelope, timeout=deadline - time.monotonic())
            response = self._wait_json(f"response-{request_id}.json",
                prefix.with_name(prefix.name + "-session-response.json"), deadline)
            self._validate(response, request_id=request_id, filename=filename, root_wait_ms=ROOT_WAIT_MS)
            self._validate_child_prefetch(response)
            result = response.get("result")
            code = response.get("code")
            if not isinstance(result, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                     for k, v in result.items()):
                raise RuntimeError("UiAutomation session result is malformed")
            for key in ("child_prefetch_mode", "sdk_api", "child_query_strategy"):
                if key in result and result[key] != str(response[key]):
                    raise RuntimeError(f"UiAutomation session result mismatch for {key}")
            if type(code) is not int or (result.get("snapshot"), code) not in (("ok", -1), ("failed", 0)):
                raise RuntimeError("UiAutomation session result/code disagree")
            if result.get("snapshot") == "ok" and result.get("filename") != filename:
                raise RuntimeError("UiAutomation session result filename does not match its request")
            self._event("response", request_id=request_id, filename=filename,
                        snapshot=result["snapshot"], wait_ms=result.get("wait_ms"),
                        elapsed_seconds=time.monotonic() - started)
            if time.monotonic() >= deadline:
                raise RuntimeError("UiAutomation session timed out after its matching response")
            if code != -1:
                return result, None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError("UiAutomation session timed out before reading matching XML")
            xml = self._run(["shell", "run-as", HELPER, "cat", f"{self.directory}/{filename}"], timeout=remaining)
            if xml.returncode:
                raise RuntimeError("UiAutomation session did not return its matching XML")
            if time.monotonic() >= deadline:
                raise RuntimeError("UiAutomation session timed out while reading matching XML")
            self._check_pipe_error()
            return result, xml.stdout.decode("utf-8")
        except (OSError, RuntimeError, ValueError) as error:
            self.fatal_error = str(error)
            self._event("protocol-failed", request_id=request_id, filename=filename, error=str(error))
            raise

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        if not self.started:
            return
        if self.process is None:
            self._event("closed-without-process")
            return
        try:
            self._write("stop.json", {"protocol": PROTOCOL, "nonce": self.nonce}, timeout=5)
            stdout, stderr = self._finish_readers(time.monotonic() + 10)
            self._instrumentation_evidence(stdout, stderr)
            self._check_pipe_error()
            if self._publications:
                raise RuntimeError("UiAutomation session unconsumed publication notice at close")
            transcript = (stdout + stderr).decode("utf-8", "replace")
            if self.process.returncode or not re.search(r"INSTRUMENTATION_CODE:\s*-1\b", transcript):
                raise RuntimeError("UiAutomation session did not finish normally")
            closed = self._run(["shell", "run-as", HELPER, "cat", f"{self.directory}/closed.json"], timeout=5)
            if closed.returncode:
                raise RuntimeError("UiAutomation session has no matching close acknowledgement")
            (self.output / "ui-snapshot-session-closed.json").write_bytes(closed.stdout)
            self._validate(json.loads(closed.stdout), state="closed")
            cleanup = self._run(["shell", "run-as", HELPER, "rm", "-r", self.directory], timeout=5)
            if cleanup.returncode:
                raise RuntimeError("UiAutomation session private-file cleanup failed")
            self._event("closed")
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
            self._event("close-failed", error=str(error))
            # Release only this owned test helper if graceful protocol shutdown
            # failed. This cannot turn the run green or change the App process.
            try:
                self._run(["shell", "am", "force-stop", HELPER], timeout=5)
            finally:
                if self.process.poll() is None:
                    self.process.terminate()
                try:
                    stdout, stderr = self._finish_readers(time.monotonic() + 5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    stdout, stderr = self._finish_readers(time.monotonic() + 5)
                self._instrumentation_evidence(stdout, stderr)
            raise RuntimeError(f"UiAutomation session cleanup failed: {error}") from error
