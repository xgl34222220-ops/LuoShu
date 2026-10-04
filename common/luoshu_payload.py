#!/usr/bin/env python3
"""LuoShu next-boot payload format: manifest schema and integrity validation.

The engine writes payloads in this format; next-boot staging, self-mount and
rollback validate them with ``--validate-payload-only`` before mounting.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

SCHEMA = "universal-font-deployment-v1"
DEPLOYMENT_REVISION = 1
ALLOWED_PARTITIONS = {
    "system", "system_ext", "product", "vendor", "odm", "oem",
    "my_product", "my_engineering", "my_company", "my_preload",
    "my_region", "my_stock", "oplus_product", "oplus_engineering",
    "oplus_version", "oplus_region", "mi_ext", "cust", "hw_product",
}
BACKEND_PROFILES = {
    "Magisk": {"mountStage": "post-fs-data", "backend": "self-mount"},
    "KernelSU": {"mountStage": "post-mount", "backend": "self-mount"},
    "APatch": {"mountStage": "post-mount", "backend": "self-mount"},
}


class DeploymentError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentError(f"无法读取 JSON：{path}") from error
    if not isinstance(value, dict):
        raise DeploymentError(f"JSON 根节点无效：{path}")
    return value


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise DeploymentError(f"无法读取文件：{path}") from error
    return digest.hexdigest()


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f".tmp.{os.getpid()}")
    try:
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _safe_logical(path_value: str, *, dynamic: bool = False) -> Path:
    path = Path(path_value)
    parts = path.parts
    if not parts or parts[0] != "/":
        raise DeploymentError(f"逻辑路径必须是绝对路径：{path_value}")
    if any(part in {"", ".", ".."} for part in parts[1:]):
        raise DeploymentError(f"逻辑路径包含非法组件：{path_value}")
    if dynamic:
        if len(parts) < 4 or parts[1] != "data" or parts[2] != "fonts":
            raise DeploymentError(f"动态字体目标不在 /data/fonts：{path_value}")
        return path
    if len(parts) < 3 or parts[1] not in ALLOWED_PARTITIONS:
        raise DeploymentError(f"不支持的系统字体分区：{path_value}")
    return path


def _payload_relative(logical: Path) -> Path:
    return Path(*logical.parts[1:])


def _payload_digest(files: list[dict[str, Any]], dynamics: list[dict[str, Any]]) -> str:
    material = {
        "files": [
            {
                "kind": item["kind"],
                "logicalPath": item["logicalPath"],
                "payloadPath": item["payloadPath"],
                "sha256": item["sha256"],
                "bytes": item["bytes"],
                "artifactId": item.get("artifactId", ""),
                "sourceXml": item.get("sourceXml", ""),
            }
            for item in sorted(files, key=lambda value: value["logicalPath"])
        ],
        "dynamicMounts": [
            {
                "targetPath": item["targetPath"],
                "sourcePayloadPath": item["sourcePayloadPath"],
                "sha256": item["sha256"],
                "artifactId": item["artifactId"],
            }
            for item in sorted(dynamics, key=lambda value: value["targetPath"])
        ],
    }
    return f"sha256:{_canonical_hash(material)}"


def validate_payload_integrity(
    deployment: dict[str, Any],
    payload_root: Path | None = None,
) -> None:
    if deployment.get("schema") != SCHEMA:
        raise DeploymentError("Deployment manifest schema 无效")
    if int(deployment.get("deploymentRevision") or 0) != DEPLOYMENT_REVISION:
        raise DeploymentError("Deployment revision 无效")
    if deployment.get("mutatesSystem") is not False or deployment.get("backendNeutral") is not True:
        raise DeploymentError("Deployment manifest 安全属性无效")
    if deployment.get("backendProfiles") != BACKEND_PROFILES:
        raise DeploymentError("Deployment backend profiles 已被修改")

    files = deployment.get("files")
    dynamic = deployment.get("dynamicMounts")
    summary = deployment.get("summary")
    if not isinstance(files, list) or not isinstance(dynamic, list) or not isinstance(summary, dict):
        raise DeploymentError("Deployment manifest 结构无效")

    seen_logical: set[str] = set()
    partitions: set[str] = set()
    for item in files:
        if not isinstance(item, dict):
            raise DeploymentError("Deployment file 条目无效")
        logical = str(item.get("logicalPath") or "")
        _safe_logical(logical)
        if logical in seen_logical:
            raise DeploymentError(f"Deployment 逻辑路径重复：{logical}")
        seen_logical.add(logical)
        partitions.add(Path(logical).parts[1])
        if payload_root is not None:
            payload = payload_root / str(item.get("payloadPath") or "")
            if not payload.is_file():
                raise DeploymentError(f"Deployment payload 文件缺失：{payload}")
            if _sha256(payload) != item.get("sha256"):
                raise DeploymentError(f"Deployment payload 摘要不一致：{payload}")

    seen_dynamic: set[str] = set()
    for item in dynamic:
        if not isinstance(item, dict) or item.get("readOnly") is not True:
            raise DeploymentError("Dynamic mount 条目无效")
        target = str(item.get("targetPath") or "")
        _safe_logical(target, dynamic=True)
        if target in seen_dynamic:
            raise DeploymentError(f"Dynamic mount 目标重复：{target}")
        seen_dynamic.add(target)
        if payload_root is not None:
            source = payload_root / str(item.get("sourcePayloadPath") or "")
            if not source.is_file() or _sha256(source) != item.get("sha256"):
                raise DeploymentError(f"Dynamic mount 源文件缺失或摘要变化：{target}")

    expected_summary = {
        "fileCount": len(files),
        "fontFileCount": sum(item.get("kind") != "xml" for item in files),
        "xmlFileCount": sum(item.get("kind") == "xml" for item in files),
        "dynamicMountCount": len(dynamic),
        "partitionCount": len(partitions),
        "backendCount": len(BACKEND_PROFILES),
        "activationReady": True,
        "executableNow": False,
    }
    if summary != expected_summary:
        raise DeploymentError("Deployment summary 与 payload 不一致")

    expected_digest = _payload_digest(files, dynamic)
    if deployment.get("payloadDigest") != expected_digest:
        raise DeploymentError("Deployment payloadDigest 完整性校验失败")

    verification_contracts = deployment.get("verificationContracts")
    if verification_contracts is not None:
        if not isinstance(verification_contracts, dict):
            raise DeploymentError("Deployment verificationContracts 无效")
        specs = (
            ("fontPlan", "planId", deployment.get("fontPlanId"), ".luoshu-runtime/deployment/font-plan.json"),
            ("artifactManifest", "manifestId", deployment.get("artifactManifestId"), ".luoshu-runtime/deployment/artifact-manifest.json"),
        )
        for name, id_key, expected_id_value, expected_path in specs:
            contract = verification_contracts.get(name)
            if not isinstance(contract, dict):
                raise DeploymentError(f"Deployment verification contract 缺失：{name}")
            if contract.get("payloadPath") != expected_path:
                raise DeploymentError(f"Deployment verification contract 路径无效：{name}")
            if contract.get(id_key) != expected_id_value:
                raise DeploymentError(f"Deployment verification contract 身份不一致：{name}")
            digest = str(contract.get("sha256") or "")
            if len(digest) != 64:
                raise DeploymentError(f"Deployment verification contract 摘要无效：{name}")
            if payload_root is not None:
                snapshot = payload_root / expected_path
                if not snapshot.is_file() or _sha256(snapshot) != digest:
                    raise DeploymentError(f"Deployment verification contract 缺失或摘要变化：{name}")

    semantic = {
        "fontPlanId": deployment.get("fontPlanId"),
        "routeId": deployment.get("routeId"),
        "artifactManifestId": deployment.get("artifactManifestId"),
        "payloadDigest": deployment.get("payloadDigest"),
        "files": files,
        "dynamicMounts": dynamic,
        "backendProfiles": BACKEND_PROFILES,
    }
    if verification_contracts is not None:
        semantic["verificationContracts"] = verification_contracts
    expected_id = f"sha256:{_canonical_hash(semantic)}"
    if deployment.get("deploymentId") != expected_id:
        raise DeploymentError("Deployment deploymentId 完整性校验失败")

    runtime_manifest = deployment.get("runtimeManifest")
    if runtime_manifest is not None:
        if not isinstance(runtime_manifest, dict):
            raise DeploymentError("Deployment runtimeManifest 无效")
        if runtime_manifest.get("deploymentId") != deployment.get("deploymentId"):
            raise DeploymentError("Deployment runtimeManifest 与 deploymentId 不一致")
        if payload_root is not None:
            runtime_path = payload_root / str(runtime_manifest.get("payloadPath") or "")
            if not runtime_path.is_file():
                raise DeploymentError("Deployment runtime manifest 文件缺失")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--payload-root", type=Path)
    parser.add_argument("--validate-payload-only", type=Path, required=True)
    args = parser.parse_args()
    try:
        deployment = _load(args.validate_payload_only)
        validate_payload_integrity(deployment, args.payload_root)
    except DeploymentError as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False))
        return 1
    print(json.dumps({
        "status": "ok",
        "schema": deployment["schema"],
        "deploymentId": deployment["deploymentId"],
        "payloadDigest": deployment["payloadDigest"],
        **deployment["summary"],
    }, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
