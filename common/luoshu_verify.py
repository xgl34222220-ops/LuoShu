#!/usr/bin/env python3
"""Boot verification for engine v3 payloads.

Runs once after boot_completed. FAIL (the caller then stages a rollback) when the
payload this boot was supposed to mount is not what the system sees: runtime or
mount state disagree with the deployment, or a payload file is missing or
different at its system path. A FontManager dump that never mentions a replaced
file is only a warning: its format differs between ROMs.

Output keeps the Phase 8 result format, so App status and rollback are unchanged.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import luoshu_payload

SCHEMA = "universal-font-runtime-verification-v1"
REVISION = 2


def _conf(path: Path | None) -> dict[str, str]:
    if path is None or not path.is_file():
        return {}
    result = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            result[key.strip()] = value.strip()
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _visible(logical: str, root: Path | None) -> Path:
    return root / logical.lstrip("/") if root is not None else Path(logical)


def verify(
    deployment: dict[str, Any],
    *,
    runtime_conf: dict[str, str],
    mount_state: dict[str, str],
    font_dump: str,
    active_font: str,
    visible_root: Path | None = None,
    boot_id: str = "",
) -> dict[str, Any]:
    luoshu_payload.validate_payload_integrity(deployment)
    failures: list[str] = []
    warnings: list[str] = []
    deployment_id = str(deployment.get("deploymentId") or "")
    digest = str(deployment.get("payloadDigest") or "")

    if not runtime_conf:
        failures.append("runtime-state-missing")
    else:
        if runtime_conf.get("state") != "active":
            failures.append("runtime-state-not-active")
        if runtime_conf.get("deploymentId") != deployment_id:
            failures.append("runtime-deployment-id-mismatch")
        if runtime_conf.get("payloadDigest") != digest:
            failures.append("runtime-payload-digest-mismatch")
    if not mount_state:
        failures.append("mount-state-missing")
    else:
        if mount_state.get("state") != "mounted":
            failures.append("mount-transaction-not-mounted")
        if mount_state.get("deploymentId") and mount_state.get("deploymentId") != deployment_id:
            failures.append("mount-deployment-id-mismatch")

    files = []
    font_files = 0
    hits = 0
    dump = font_dump.lower()
    for item in deployment.get("files") or []:
        logical = str(item.get("logicalPath") or "")
        visible = _visible(logical, visible_root)
        report = {"kind": item.get("kind"), "logicalPath": logical, "status": "ok"}
        if not visible.is_file():
            failures.append(f"visible-file-missing:{logical}")
            report["status"] = "missing"
        elif _sha256(visible) != item.get("sha256"):
            failures.append(f"visible-file-hash-mismatch:{logical}")
            report["status"] = "hash-mismatch"
        files.append(report)
        if item.get("kind") != "xml":
            font_files += 1
            if Path(logical).name.lower() in dump:
                hits += 1
    if dump.strip() and font_files and not hits:
        warnings.append("font-manager-no-replaced-file-reference")

    grade = "FAIL" if failures else "WARN" if warnings else "PASS"
    return {
        "schema": SCHEMA,
        "verificationRevision": REVISION,
        "engine": "luoshu-engine-v3",
        "grade": grade,
        "state": grade.lower(),
        "mode": "universal-runtime",
        "reason": failures[0] if failures else warnings[0] if warnings else "verified",
        "activeFont": active_font,
        "deploymentId": deployment_id,
        "payloadDigest": digest,
        "bootId": boot_id,
        "time": int(time.time()),
        "summary": {
            "deploymentFiles": len(files),
            "fontFiles": font_files,
            "dynamicTargets": 0,
            "dynamicMounted": 0,
            "fontManagerHits": hits,
            "fontManagerAvailable": bool(dump.strip()),
            "failureCount": len(failures),
            "warningCount": len(warnings),
        },
        "failures": failures,
        "warnings": warnings,
        "files": files,
    }


def _write_outputs(result: dict[str, Any], output_json: Path, output_conf: Path) -> None:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    temp = output_json.with_name(f".{output_json.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    os.replace(temp, output_json)
    summary = result.get("summary") or {}
    lines = [
        f"schema={SCHEMA}",
        f"grade={result.get('grade', 'FAIL')}",
        f"state={result.get('state', 'fail')}",
        f"mode={result.get('mode', 'universal-runtime')}",
        f"reason={result.get('reason', 'verifier-error')}",
        f"activeFont={result.get('activeFont', '')}",
        f"deploymentId={result.get('deploymentId', '')}",
        f"payloadDigest={result.get('payloadDigest', '')}",
        f"bootId={result.get('bootId', '')}",
        f"fontFiles={summary.get('fontFiles', 0)}",
        "dynamicTargets=0",
        "dynamicMounted=0",
        f"fontManagerHits={summary.get('fontManagerHits', 0)}",
        f"failureCount={summary.get('failureCount', 0)}",
        f"warningCount={summary.get('warningCount', 0)}",
        f"time={result.get('time', int(time.time()))}",
    ]
    temp = output_conf.with_name(f".{output_conf.name}.{os.getpid()}.tmp")
    temp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(temp, 0o644)
    os.replace(temp, output_conf)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--deployment", required=True, type=Path)
    parser.add_argument("--runtime-conf", type=Path)
    parser.add_argument("--mount-state", type=Path)
    parser.add_argument("--font-dump", type=Path)
    parser.add_argument("--visible-root", type=Path)
    parser.add_argument("--active-font", default="")
    parser.add_argument("--boot-id", default="")
    parser.add_argument("--output-json", required=True, type=Path)
    parser.add_argument("--output-conf", required=True, type=Path)
    args = parser.parse_args()
    try:
        deployment = json.loads(args.deployment.read_text(encoding="utf-8"))
        dump = args.font_dump.read_text(encoding="utf-8", errors="replace") \
            if args.font_dump and args.font_dump.is_file() else ""
        result = verify(
            deployment,
            runtime_conf=_conf(args.runtime_conf),
            mount_state=_conf(args.mount_state),
            font_dump=dump,
            active_font=args.active_font,
            visible_root=args.visible_root,
            boot_id=args.boot_id,
        )
    except (OSError, ValueError, luoshu_payload.DeploymentError) as error:
        result = {
            "schema": SCHEMA, "verificationRevision": REVISION, "grade": "FAIL", "state": "fail",
            "mode": "universal-runtime", "reason": "verifier-error", "activeFont": args.active_font,
            "bootId": args.boot_id, "time": int(time.time()), "message": str(error),
            "summary": {"failureCount": 1, "warningCount": 0}, "failures": ["verifier-error"], "warnings": [],
        }
    _write_outputs(result, args.output_json, args.output_conf)
    print(json.dumps({"status": "ok", "grade": result["grade"], "reason": result["reason"]}, ensure_ascii=False))
    return 0 if result["grade"] != "FAIL" else 3


if __name__ == "__main__":
    raise SystemExit(main())
