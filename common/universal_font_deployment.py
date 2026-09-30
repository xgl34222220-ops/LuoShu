#!/usr/bin/env python3
"""Build a backend-neutral LuoShu Phase 7 deployment payload.

Consumes validated Phase 4/5/6 artifacts. It never reclassifies fonts and never
chooses new targets. The exact same payload is consumed by Magisk, KernelSU and
APatch; only boot hook timing differs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import minimal_xml_router
import universal_font_compiler
import universal_font_plan

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


def _copy_verified(source: Path, expected_sha: str, destination: Path) -> dict[str, Any]:
    if not source.is_file():
        raise DeploymentError(f"编译 artifact 不存在：{source}")
    actual = _sha256(source)
    if actual != expected_sha:
        raise DeploymentError(f"编译 artifact 摘要变化：{source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chmod(destination, 0o644)
    copied = _sha256(destination)
    if copied != expected_sha:
        raise DeploymentError(f"部署副本摘要不一致：{destination}")
    return {
        "sha256": copied,
        "bytes": int(destination.stat().st_size),
    }


def _artifact_index(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise DeploymentError("Artifact manifest 缺少 artifacts")
    for item in artifacts:
        if not isinstance(item, dict) or item.get("status") != "ready":
            continue
        artifact_id = str(item.get("artifactId") or "")
        path = Path(str(item.get("output") or ""))
        sha = str(item.get("sha256") or "")
        if not artifact_id.startswith("ufc:") or not path.is_file() or len(sha) != 64:
            raise DeploymentError(f"Ready artifact 无效：{artifact_id}")
        result[artifact_id] = item
    return result


def _record_file(
    records: dict[str, dict[str, Any]],
    logical: str,
    payload_rel: str,
    *,
    kind: str,
    sha256: str,
    bytes_count: int,
    artifact_id: str = "",
    source_xml: str = "",
) -> None:
    prior = records.get(logical)
    value = {
        "kind": kind,
        "logicalPath": logical,
        "payloadPath": payload_rel,
        "sha256": sha256,
        "bytes": int(bytes_count),
        "artifactId": artifact_id,
        "sourceXml": source_xml,
    }
    if prior is not None and prior != value:
        raise DeploymentError(f"多个部署对象争用同一逻辑路径：{logical}")
    records[logical] = value


def _artifact_destination_for_xml(target_path: str, filename: str) -> Path:
    target = _safe_logical(target_path)
    parent = target.parent
    if parent.name != "fonts":
        raise DeploymentError(f"XML 路由目标不在字体目录：{target_path}")
    return parent / filename


def _write_dynamic_runtime(stage: Path, mounts: list[dict[str, Any]]) -> None:
    runtime = stage / ".luoshu-runtime/deployment"
    runtime.mkdir(parents=True, exist_ok=True)
    conf = runtime / "dynamic-mounts.conf"
    with conf.open("w", encoding="utf-8") as stream:
        for item in mounts:
            stream.write(
                f"{item['sourcePayloadPath']}|{item['targetPath']}|{item['sha256']}\n"
            )
    os.chmod(conf, 0o600)


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
                **({"dynamicIdentity": item["dynamicIdentity"]} if item.get("dynamicIdentity") else {}),
            }
            for item in sorted(dynamics, key=lambda value: value["targetPath"])
        ],
    }
    return f"sha256:{_canonical_hash(material)}"


def build_deployment(
    font_plan: dict[str, Any],
    route_plan: dict[str, Any],
    artifact_manifest: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    universal_font_plan.validate_plan(font_plan)
    minimal_xml_router.validate_route_plan(route_plan, font_plan=font_plan)
    universal_font_compiler.validate_manifest(artifact_manifest, font_plan, route_plan)

    summary = artifact_manifest.get("summary") if isinstance(artifact_manifest.get("summary"), dict) else {}
    if int(summary.get("blockedCount") or 0) != 0:
        raise DeploymentError("存在 blocked artifact，拒绝生成部署 payload")
    if route_plan.get("summary", {}).get("routingComplete") is not True:
        raise DeploymentError("XML RoutePlan 不完整，拒绝生成部署 payload")

    artifacts = _artifact_index(artifact_manifest)
    artifact_map = artifact_manifest.get("artifactMap")
    physical_map = artifact_manifest.get("physicalTargetMap")
    dynamic_map = artifact_manifest.get("dynamicTargetMap")
    if not isinstance(artifact_map, dict) or not isinstance(physical_map, dict) or not isinstance(dynamic_map, dict):
        raise DeploymentError("Artifact manifest 缺少部署映射")

    parent = output_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    stage: Path | None = Path(tempfile.mkdtemp(prefix=f".{output_root.name}.", dir=parent))
    files: dict[str, dict[str, Any]] = {}
    dynamic_mounts: list[dict[str, Any]] = []
    dynamic_targets: set[str] = set()

    try:
        # Render Phase 5 XML first. The renderer checks source XML digests and
        # proves that only planned font.text nodes change.
        minimal_xml_router.render_all(
            route_plan,
            {str(k): str(v) for k, v in artifact_map.items()},
            stage,
        )

        documents = route_plan.get("documents") if isinstance(route_plan.get("documents"), dict) else {}
        for source_xml, document in documents.items():
            if not isinstance(document, dict) or not document.get("operations"):
                continue
            logical_xml = _safe_logical(str(source_xml))
            rendered = stage / _payload_relative(logical_xml)
            if not rendered.is_file():
                raise DeploymentError(f"渲染后的 XML 缺失：{source_xml}")
            _record_file(
                files,
                str(logical_xml),
                str(_payload_relative(logical_xml)),
                kind="xml",
                sha256=_sha256(rendered),
                bytes_count=int(rendered.stat().st_size),
                source_xml=str(source_xml),
            )
            for operation in document.get("operations") or []:
                artifact = operation.get("artifact") if isinstance(operation, dict) else None
                if not isinstance(artifact, dict):
                    continue
                artifact_id = str(artifact.get("artifactId") or "")
                compiled = artifacts.get(artifact_id)
                if compiled is None:
                    raise DeploymentError(f"XML Route 缺少 ready artifact：{artifact_id}")
                filename = str(artifact_map.get(artifact_id) or "")
                if not filename or Path(filename).name != filename:
                    raise DeploymentError(f"XML artifact 文件名无效：{artifact_id}")
                logical_font = _artifact_destination_for_xml(
                    str(operation.get("targetPath") or ""),
                    filename,
                )
                rel = _payload_relative(logical_font)
                destination = stage / rel
                details = _copy_verified(
                    Path(str(compiled["output"])),
                    str(compiled["sha256"]),
                    destination,
                )
                _record_file(
                    files,
                    str(logical_font),
                    str(rel),
                    kind="xml-font",
                    sha256=details["sha256"],
                    bytes_count=details["bytes"],
                    artifact_id=artifact_id,
                    source_xml=str(source_xml),
                )

        # Physical-only targets keep the exact ROM logical path.
        for logical_value, artifact_id_raw in sorted(physical_map.items()):
            logical = _safe_logical(str(logical_value))
            artifact_id = str(artifact_id_raw)
            compiled = artifacts.get(artifact_id)
            if compiled is None:
                raise DeploymentError(f"Physical target 缺少 ready artifact：{artifact_id}")
            rel = _payload_relative(logical)
            details = _copy_verified(
                Path(str(compiled["output"])),
                str(compiled["sha256"]),
                stage / rel,
            )
            _record_file(
                files,
                str(logical),
                str(rel),
                kind="physical-font",
                sha256=details["sha256"],
                bytes_count=details["bytes"],
                artifact_id=artifact_id,
            )

        # Dynamic targets are not placed in the partition overlay. They are kept
        # in a private source directory and read-only bind-mounted to /data/fonts.
        dynamic_source_root = stage / ".luoshu-dynamic"
        for target_value, artifact_id_raw in sorted(dynamic_map.items()):
            target = _safe_logical(str(target_value), dynamic=True)
            target_text = str(target)
            if target_text in dynamic_targets:
                raise DeploymentError(f"重复动态字体目标：{target_text}")
            dynamic_targets.add(target_text)
            artifact_id = str(artifact_id_raw)
            compiled = artifacts.get(artifact_id)
            if compiled is None:
                raise DeploymentError(f"Dynamic target 缺少 ready artifact：{artifact_id}")
            suffix = Path(str(compiled.get("output") or "")).suffix.lower()
            safe_id = artifact_id.replace(":", "-")
            source_rel = Path(".luoshu-dynamic") / f"{safe_id}{suffix}"
            details = _copy_verified(
                Path(str(compiled["output"])),
                str(compiled["sha256"]),
                stage / source_rel,
            )
            dynamic_mounts.append({
                "targetPath": target_text,
                "sourcePayloadPath": str(source_rel),
                "sha256": details["sha256"],
                "bytes": details["bytes"],
                "artifactId": artifact_id,
                "readOnly": True,
                **({"dynamicIdentity": copy.deepcopy(font_plan["targets"][target_text]["targetContract"]["dynamicIdentity"])}
                   if font_plan.get("targets", {}).get(target_text, {}).get("targetContract", {}).get("dynamicIdentity") else {}),
            })

        _write_dynamic_runtime(stage, dynamic_mounts)

        # Freeze the exact Phase 4/6 verification contracts inside this payload.
        # Phase 8 must verify the deployment that was actually staged, not a
        # mutable config copy that may be rebuilt after stage-next.
        contract_root = stage / ".luoshu-runtime/deployment"
        plan_snapshot = contract_root / "font-plan.json"
        artifact_snapshot = contract_root / "artifact-manifest.json"

        # Strip non-semantic timestamps/cache locations before hashing the
        # snapshots so an identical frozen plan still yields the same
        # deployment identity across repeated prepare calls.
        plan_contract = copy.deepcopy(font_plan)
        plan_contract.pop("generatedAt", None)
        artifact_contract = copy.deepcopy(artifact_manifest)
        artifact_contract.pop("generatedAt", None)
        for item in artifact_contract.get("artifacts") or []:
            if isinstance(item, dict):
                item.pop("output", None)
                item.pop("stock", None)
        _atomic_json(plan_snapshot, plan_contract)
        _atomic_json(artifact_snapshot, artifact_contract)
        verification_contracts = {
            "fontPlan": {
                "payloadPath": ".luoshu-runtime/deployment/font-plan.json",
                "sha256": _sha256(plan_snapshot),
                "planId": font_plan.get("planId"),
            },
            "artifactManifest": {
                "payloadPath": ".luoshu-runtime/deployment/artifact-manifest.json",
                "sha256": _sha256(artifact_snapshot),
                "manifestId": artifact_manifest.get("manifestId"),
            },
        }

        file_list = sorted(files.values(), key=lambda value: value["logicalPath"])
        payload_digest = _payload_digest(file_list, dynamic_mounts)
        partitions = sorted({
            Path(item["logicalPath"]).parts[1]
            for item in file_list
            if item["logicalPath"].startswith("/")
        })
        deployment_semantic = {
            "fontPlanId": font_plan.get("planId"),
            "routeId": route_plan.get("routeId"),
            "artifactManifestId": artifact_manifest.get("manifestId"),
            "payloadDigest": payload_digest,
            "files": file_list,
            "dynamicMounts": dynamic_mounts,
            "backendProfiles": BACKEND_PROFILES,
            "verificationContracts": verification_contracts,
        }
        deployment_id = f"sha256:{_canonical_hash(deployment_semantic)}"
        payload = {
            "schema": SCHEMA,
            "deploymentRevision": DEPLOYMENT_REVISION,
            "state": "prepared",
            "generatedAt": int(time.time()),
            "mutatesSystem": False,
            "mountsAtBoot": True,
            "backendNeutral": True,
            "deploymentId": deployment_id,
            "fontPlanId": font_plan.get("planId"),
            "routeId": route_plan.get("routeId"),
            "artifactManifestId": artifact_manifest.get("manifestId"),
            "payloadDigest": payload_digest,
            "summary": {
                "fileCount": len(file_list),
                "fontFileCount": sum(item["kind"] != "xml" for item in file_list),
                "xmlFileCount": sum(item["kind"] == "xml" for item in file_list),
                "dynamicMountCount": len(dynamic_mounts),
                "partitionCount": len(partitions),
                "backendCount": len(BACKEND_PROFILES),
                "activationReady": True,
                "executableNow": False,
            },
            "partitions": partitions,
            "backendProfiles": copy.deepcopy(BACKEND_PROFILES),
            "files": file_list,
            "dynamicMounts": dynamic_mounts,
            "verificationContracts": verification_contracts,
        }

        runtime_manifest = stage / ".luoshu-runtime/deployment/deployment.json"
        payload["runtimeManifest"] = {
            "payloadPath": ".luoshu-runtime/deployment/deployment.json",
            "deploymentId": deployment_id,
        }
        _atomic_json(runtime_manifest, payload)

        if output_root.exists():
            shutil.rmtree(output_root)
        os.replace(stage, output_root)
        stage = None
        return payload
    finally:
        if stage is not None and stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def validate_dynamic_generation(deployment: dict[str, Any], visible_root: Path | None = None) -> None:
    """Check the authoritative dynamic generation again immediately before boot binding."""
    for item in deployment.get("dynamicMounts") or []:
        identity = item.get("dynamicIdentity")
        if not identity:  # Backwards-compatible sealed synthetic/older payloads.
            continue
        if not isinstance(identity, dict) or identity.get("fontPath") != item.get("targetPath"):
            raise DeploymentError("动态字体 generation identity 不匹配")
        for path_key, digest_key in (("configPath", "configSha256"), ("fontPath", "fontSha256")):
            logical = _safe_logical(str(identity.get(path_key) or ""), dynamic=True)
            path = visible_root / str(logical).lstrip("/") if visible_root else logical
            digest = str(identity.get(digest_key) or "")
            if len(digest) != 64 or not path.is_file():
                raise DeploymentError(f"动态字体 generation 证据缺失：{logical}")
            actual = _sha256(path)
            # A repeated hook may observe our already-bound compiled file; the
            # shell separately requires same-boot ownership and read-only mount.
            allowed = {digest, str(item.get("sha256") or "")} if path_key == "fontPath" else {digest}
            if actual not in allowed:
                raise DeploymentError(f"动态字体 generation 已变化：{logical}")


def _validate_execution_tree(deployment: dict[str, Any], root: Path) -> None:
    """The mount backend exposes whole trees: no undeclared bytes may enter them."""
    expected = {".luoshu-runtime/deployment/dynamic-mounts.conf",
                ".luoshu-runtime/deployment/deployment.json"}
    for item in deployment["files"]:
        logical = _safe_logical(str(item["logicalPath"]))
        relative = str(_payload_relative(logical))
        if len(logical.parts) < 4 or logical.parts[2] not in {"fonts", "etc"}:
            raise DeploymentError(f"挂载后端无法精确暴露计划路径：{logical}")
        if item.get("payloadPath") != relative:
            raise DeploymentError(f"payload 与逻辑挂载路径不一致：{logical}")
        expected.add(relative)
    for item in deployment["dynamicMounts"]:
        relative = str(item.get("sourcePayloadPath") or "")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or not relative.startswith(".luoshu-dynamic/"):
            raise DeploymentError("动态挂载源路径不受信任")
        expected.add(relative)
    for item in (deployment.get("verificationContracts") or {}).values():
        expected.add(str(item["payloadPath"]))
    actual: set[str] = set()
    for entry in root.rglob("*"):
        if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
            raise DeploymentError(f"payload 不允许链接或特殊文件：{entry}")
        if entry.is_file():
            actual.add(entry.relative_to(root).as_posix())
    if actual != expected:
        raise DeploymentError("payload 执行集合与冻结计划不一致：" +
                              str({"extra": sorted(actual - expected), "missing": sorted(expected - actual)}))
    instructions = "".join(
        f"{item['sourcePayloadPath']}|{item['targetPath']}|{item['sha256']}\n"
        for item in deployment["dynamicMounts"]
    )
    if (root / ".luoshu-runtime/deployment/dynamic-mounts.conf").read_text(encoding="utf-8") != instructions:
        raise DeploymentError("动态实际挂载指令与冻结计划不一致")
    if _load(root / ".luoshu-runtime/deployment/deployment.json") != deployment:
        raise DeploymentError("运行时 deployment 与已验证 manifest 不一致")


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

    if payload_root is not None:
        _validate_execution_tree(deployment, payload_root)


def validate_deployment(
    deployment: dict[str, Any],
    font_plan: dict[str, Any],
    route_plan: dict[str, Any],
    artifact_manifest: dict[str, Any],
    payload_root: Path | None = None,
) -> None:
    validate_payload_integrity(deployment, payload_root)
    if deployment.get("fontPlanId") != font_plan.get("planId"):
        raise DeploymentError("Deployment 与 FontPlan 不一致")
    if deployment.get("routeId") != route_plan.get("routeId"):
        raise DeploymentError("Deployment 与 RoutePlan 不一致")
    if deployment.get("artifactManifestId") != artifact_manifest.get("manifestId"):
        raise DeploymentError("Deployment 与 Artifact manifest 不一致")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--font-plan", type=Path)
    parser.add_argument("--route-plan", type=Path)
    parser.add_argument("--artifact-manifest", type=Path)
    parser.add_argument("--payload-root", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--validate-payload-only", type=Path)
    parser.add_argument("--validate-dynamic-generation", action="store_true")
    parser.add_argument("--visible-root", type=Path)
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-payload-digest")
    args = parser.parse_args()

    try:
        if args.validate_payload_only is not None:
            deployment = _load(args.validate_payload_only)
            validate_payload_integrity(deployment, args.payload_root)
            if args.expected_deployment_id is not None and args.expected_deployment_id != deployment.get("deploymentId"):
                raise DeploymentError("运行状态与实际 deploymentId 不一致")
            if args.expected_payload_digest is not None and args.expected_payload_digest != deployment.get("payloadDigest"):
                raise DeploymentError("运行状态与实际 payloadDigest 不一致")
            if args.validate_dynamic_generation:
                validate_dynamic_generation(deployment, args.visible_root)
            print(json.dumps({
                "status": "ok",
                "schema": deployment["schema"],
                "deploymentId": deployment["deploymentId"],
                "payloadDigest": deployment["payloadDigest"],
                **deployment["summary"],
            }, ensure_ascii=False, separators=(",", ":")))
            return 0

        if args.font_plan is None or args.route_plan is None or args.artifact_manifest is None:
            raise DeploymentError("缺少 --font-plan / --route-plan / --artifact-manifest")
        font_plan = _load(args.font_plan)
        route_plan = _load(args.route_plan)
        artifacts = _load(args.artifact_manifest)
        universal_font_plan.validate_plan(font_plan)
        minimal_xml_router.validate_route_plan(route_plan, font_plan=font_plan)
        universal_font_compiler.validate_manifest(artifacts, font_plan, route_plan)

        if args.validate is not None:
            deployment = _load(args.validate)
            validate_deployment(
                deployment, font_plan, route_plan, artifacts, args.payload_root
            )
        else:
            if args.payload_root is None or args.manifest is None:
                raise DeploymentError("生成部署 payload 需要 --payload-root 与 --manifest")
            deployment = build_deployment(
                font_plan, route_plan, artifacts, args.payload_root
            )
            validate_deployment(
                deployment, font_plan, route_plan, artifacts, args.payload_root
            )
            _atomic_json(args.manifest, deployment)

        print(json.dumps({
            "status": "ok",
            "schema": deployment["schema"],
            "deploymentId": deployment["deploymentId"],
            "payloadDigest": deployment["payloadDigest"],
            **deployment["summary"],
        }, ensure_ascii=False, separators=(",", ":")))
        return 0
    except Exception as error:
        print(json.dumps({
            "status": "error",
            "message": str(error) or error.__class__.__name__,
        }, ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
