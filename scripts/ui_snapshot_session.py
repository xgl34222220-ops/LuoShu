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
import time
import uuid
from pathlib import Path


HELPER = "io.github.xgl34222220.luoshu.uisnapshot"
PROTOCOL = 1
ROOT_WAIT_MS = 8000


class UiSnapshotSession:
    def __init__(self, adb_command: list[str], output: Path):
        self.adb_command = adb_command
        self.output = output
        self.nonce = uuid.uuid4().hex
        self.directory = f"files/ui-snapshot-session-{self.nonce}"
        self.process = None
        self.started = False
        self.closed = False
        self.fatal_error: str | None = None
        self.filenames: set[str] = set()
        self.events: list[dict[str, object]] = []
        self.commands: list[dict[str, object]] = []
        self.diagnostic_errors: list[str] = []

    def _diagnostic_write(self, path: Path, content: bytes) -> None:
        try:
            path.write_bytes(content)
        except Exception as error:
            # Evidence cannot replace a command's real result or primary error.
            self.diagnostic_errors.append(f"{path.name}: {type(error).__name__}: {error}")

    def _event(self, event: str, **details: object) -> None:
        self.events.append({"event": event, "monotonic_seconds": time.monotonic(), **details})
        self._diagnostic_write(self.output / "ui-snapshot-session.json", (json.dumps(
            {"protocol": PROTOCOL, "nonce": self.nonce, "events": self.events,
             "diagnostic_errors": self.diagnostic_errors},
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
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError(f"UiAutomation session timed out waiting for {basename}")
            if self.process.poll() is not None:
                raise RuntimeError("UiAutomation session exited before its matching response")
            result = self._run(["shell", "run-as", HELPER, "cat", f"{self.directory}/{basename}"],
                               timeout=remaining)
            if not result.returncode:
                evidence.write_bytes(result.stdout)
                if time.monotonic() >= deadline:
                    raise RuntimeError(f"UiAutomation session timed out while reading {basename}")
                try:
                    value = json.loads(result.stdout)
                except (ValueError, UnicodeDecodeError) as error:
                    raise RuntimeError("UiAutomation session returned malformed JSON") from error
                if not isinstance(value, dict):
                    raise RuntimeError("UiAutomation session response is not an object")
                return value
            time.sleep(min(.1, max(0, deadline - time.monotonic())))

    def _validate(self, envelope: dict[str, object], **expected: object) -> None:
        if not isinstance(envelope, dict):
            raise RuntimeError("UiAutomation session response is not an object")
        for key, value in {"protocol": PROTOCOL, "nonce": self.nonce, **expected}.items():
            if type(envelope.get(key)) is not type(value) or envelope.get(key) != value:
                raise RuntimeError(f"UiAutomation session response mismatch for {key}")

    def start(self, deadline: float) -> None:
        if self.closed or self.fatal_error:
            raise RuntimeError(self.fatal_error or "UiAutomation session is closed")
        if self.started:
            return
        self.started = True  # A broken connection is never silently restarted.
        started = time.monotonic()
        try:
            self.process = subprocess.Popen(self.adb_command + ["shell", "am", "instrument", "-w", "-r",
                "-e", "session_nonce", self.nonce, f"{HELPER}/.SnapshotInstrumentation"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self._event("started")
            ready = self._wait_json("ready.json", self.output / "ui-snapshot-session-ready.json", deadline)
            self._validate(ready, state="ready", root_wait_ms=ROOT_WAIT_MS)
            self._event("ready", root_wait_ms=ROOT_WAIT_MS, elapsed_seconds=time.monotonic() - started)
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
        self.filenames.add(filename)
        request_id = uuid.uuid4().hex
        started = time.monotonic()
        # A caller may share its original absolute deadline with this read.
        # The normal twenty-second host ceiling and server root wait stay fixed.
        deadline = min(started + 20, deadline) if deadline is not None else started + 20
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
            result = response.get("result")
            code = response.get("code")
            if not isinstance(result, dict) or not all(isinstance(k, str) and isinstance(v, str)
                                                     for k, v in result.items()):
                raise RuntimeError("UiAutomation session result is malformed")
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
            stdout, stderr = self.process.communicate(timeout=10)
            (self.output / "ui-snapshot-session-instrumentation.txt").write_bytes(stdout + stderr)
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
                    stdout, stderr = self.process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    stdout, stderr = self.process.communicate(timeout=5)
                (self.output / "ui-snapshot-session-instrumentation.txt").write_bytes(stdout + stderr)
            raise RuntimeError(f"UiAutomation session cleanup failed: {error}") from error
