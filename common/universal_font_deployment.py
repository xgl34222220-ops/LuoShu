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
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import fixed_outline_weight_match as fixed_match

import minimal_xml_router
import font_route_contract
import stock_font_view
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


class BlockedArtifactError(DeploymentError):
    def __init__(self, manifest):
        self.items = [item for item in manifest.get("artifacts", []) if item.get("status") == "blocked"]
        self.count = int((manifest.get("summary") or {}).get("blockedCount") or len(self.items))
        super().__init__("存在 blocked artifact，拒绝生成部署 payload")

    def message(self, manifest_path=None):
        def clean(value, limit):
            value = re.sub(r"(?:[A-Za-z]:[\\/]|/)[^\s,;]+", "<path>", str(value))
            value = " ".join(value.split())
            return value.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
        items = [item for item in self.items if not str(item.get("reason", "")).startswith("skipped-after-atomic-failure")]
        skipped = len(self.items) - len(items)
        examples = []
        for item in items[:2]:
            target = clean(Path(str(item.get("targetPath") or "unknown")).name, 48)
            details = item.get("errorDetails") or {}
            if item.get("errorCode") == "fixed-line-budget":
                reason = "fixed-line-budget bounds=[%s,%s] limit=[%s,%s]" % (
                    details.get("importedYMin"), details.get("importedYMax"),
                    details.get("maxDescent"), details.get("minAscent"))
            else:
                reason = item.get("reason") or item.get("errorType") or "unknown"
            reason = clean(reason, 85)
            examples.append(target + ":" + reason)
        parts = [str(self), "blocked=" + str(self.count), "failed=" + str(len(items)), "skipped=" + str(skipped), *examples]
        if manifest_path is not None:
            name = Path(manifest_path).name
            if not re.fullmatch(r"[a-f0-9]{24}\.json", name):
                name = "<artifact-manifest>.json"
            parts.append("manifest=config/universal-font-artifact-manifests/" + name)
        return "; ".join(parts)


def _error_payload(error, manifest_path=None):
    if isinstance(error, BlockedArtifactError):
        return {"status": "error", "code": "blocked-artifacts", "message": error.message(manifest_path)}
    return {"status": "error", "message": str(error) or error.__class__.__name__}


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
                **({"artifactIds": item["artifactIds"], "sourceXmls": item["sourceXmls"]} if "artifactIds" in item else {}),
                **({"originalIds": item["originalIds"]} if "originalIds" in item else {}),
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


def _record_shared_static(records, logical, relative, details, artifact_id, source_xml, kind='xml-static-font'):
    prior = records.get(logical)
    if prior is None:
        _record_file(records, logical, relative, kind=kind,
                     sha256=details["sha256"], bytes_count=details["bytes"], artifact_id=artifact_id)
        prior = records[logical]; prior["artifactIds"] = []; prior["sourceXmls"] = []
    if (prior.get("kind") != kind or prior.get("sha256") != details["sha256"]
            or prior.get("payloadPath") != relative or prior.get("bytes") != details["bytes"]):
        raise DeploymentError("shared static render conflicts at " + logical)
    prior["artifactIds"] = sorted(set(prior["artifactIds"] + [artifact_id]))
    prior["artifactId"] = prior["artifactIds"][0]
    prior["sourceXmls"] = sorted(set(prior["sourceXmls"] + [source_xml]))


def _copy_retained_originals(route_plan, stage, records):
    if route_plan.get("schema") != "fixed-static-xml-route-plan-v1":
        return
    raw_map = os.environ.get("LUOSHU_STOCK_FONT_MAP")
    stock_paths = universal_font_compiler._stock_map(Path(raw_map) if raw_map else None)
    with stock_font_view.session(stage.parent):
        for original_id, original in sorted(route_plan["retainedOriginals"].items()):
            target = original["target"]
            stock = universal_font_compiler._resolve_stock(original["targetPath"], stock_paths, False, target=target)
            import fixed_static_xml_compiler
            evidence = fixed_static_xml_compiler.verify_original_face(target, stock, original["faceIndex"])
            if evidence.get("sha256") != original["sha256"]:
                raise DeploymentError("retained fallback differs from captured original")
            face = universal_font_compiler._open_face(stock, original["faceIndex"], lazy=True)
            face.close()
            logical = _safe_logical(original["assetRoot"] + "/" + original["fileName"])
            relative = str(_payload_relative(logical))
            details = _copy_verified(stock, original["sha256"], stage / relative)
            prior = records.get(str(logical))
            if prior is None:
                _record_file(records, str(logical), relative, kind="xml-original",
                             sha256=details["sha256"], bytes_count=details["bytes"])
                prior = records[str(logical)]; prior["originalIds"] = []
            if prior.get("kind") != "xml-original" or prior.get("sha256") != original["sha256"]:
                raise DeploymentError("retained original collides with generated payload")
            prior["originalIds"] = sorted(set(prior["originalIds"] + [original_id]))


def build_deployment(
    font_plan: dict[str, Any],
    route_plan: dict[str, Any],
    artifact_manifest: dict[str, Any],
    output_root: Path,
) -> dict[str, Any]:
    universal_font_plan.validate_plan(font_plan)
    font_route_contract.validate_route_plan(route_plan, font_plan=font_plan)
    universal_font_compiler.validate_manifest(artifact_manifest, font_plan, route_plan)

    summary = artifact_manifest.get("summary") if isinstance(artifact_manifest.get("summary"), dict) else {}
    if int(summary.get("blockedCount") or 0) != 0:
        raise BlockedArtifactError(artifact_manifest)
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
        font_route_contract.render_all(
            route_plan,
            {str(k): str(v) for k, v in artifact_map.items()},
            stage,
            compiled_bindings=artifact_manifest.get("staticXmlBindings") or {},
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
                if artifact.get("representation") in fixed_match.REPRESENTATIONS:
                    logical_font = _safe_logical(str(operation.get("assetRoot") or "") + "/" + filename)
                else:
                    logical_font = _artifact_destination_for_xml(str(operation.get("targetPath") or ""), filename)
                rel = _payload_relative(logical_font)
                destination = stage / rel
                details = _copy_verified(
                    Path(str(compiled["output"])),
                    str(compiled["sha256"]),
                    destination,
                )
                if artifact.get("representation") in fixed_match.REPRESENTATIONS:
                    _record_shared_static(files, str(logical_font), str(rel), details, artifact_id, str(source_xml),
                                          'xml-matching-font' if artifact['representation']==fixed_match.MATCHING else 'xml-static-font')
                else:
                    _record_file(files, str(logical_font), str(rel), kind="xml-font",
                                 sha256=details["sha256"], bytes_count=details["bytes"],
                                 artifact_id=artifact_id, source_xml=str(source_xml))

        _copy_retained_originals(route_plan, stage, files)

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

        if route_plan.get("schema") == "fixed-static-xml-route-plan-v1":
            route_snapshot = contract_root / "fixed-static-route-plan.json"
            frozen_route = copy.deepcopy(route_plan)
            for doc in frozen_route["documents"].values(): doc.pop("sourcePath", None)
            for doc in frozen_route["legacyRoutePlan"]["documents"].values(): doc.pop("sourcePath", None)
            _atomic_json(route_snapshot, frozen_route)
            verification_contracts["fixedStaticRoute"] = {
                "payloadPath": ".luoshu-runtime/deployment/fixed-static-route-plan.json",
                "sha256": _sha256(route_snapshot), "routeId": route_plan["routeId"],
                "dynamicFontGeneration": copy.deepcopy(route_plan["dynamicFontGeneration"])}

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


def validate_device_generation(deployment: dict[str, Any], payload_root: Path | None) -> None:
    """Refuse a queued or live payload prepared for a different firmware build.

    Read the existing sealed FontPlan, not mutable inventory or caller-supplied
    expected identity. This check is repeated before activation and mounting.
    """
    if payload_root is None:
        raise DeploymentError("设备构建校验缺少 payload root")
    contract = (deployment.get("verificationContracts") or {}).get("fontPlan")
    expected_path = ".luoshu-runtime/deployment/font-plan.json"
    if not isinstance(contract, dict) or contract.get("payloadPath") != expected_path:
        raise DeploymentError("设备构建封印缺失，需要重新生成字体负载")
    snapshot = payload_root / expected_path
    if not snapshot.is_file() or snapshot.is_symlink() or _sha256(snapshot) != contract.get("sha256"):
        raise DeploymentError("设备构建封印不完整，拒绝激活")
    plan = _load(snapshot)
    if plan.get("planId") != deployment.get("fontPlanId") or plan.get("planId") != contract.get("planId"):
        raise DeploymentError("设备构建封印身份不一致")
    expected = (plan.get("device") or {}).get("buildKey")
    if not isinstance(expected, str) or not expected.strip() or expected.strip().lower() == "unknown":
        raise DeploymentError("原设备构建身份未知，需要重新生成字体负载")
    from font_inventory import current_build_key
    current, _fingerprint, _display = current_build_key(None)
    if not current or current.strip().lower() == "unknown":
        raise DeploymentError("无法读取当前系统构建，拒绝激活字体负载")
    if current != expected:
        raise DeploymentError("系统构建已变化，拒绝旧字体负载；请重新扫描并生成")
    universal_font_plan.validate_plan(plan, expected_build_key=current)


def validate_dynamic_generation(deployment: dict[str, Any], visible_root: Path | None = None) -> None:
    """Check the authoritative dynamic generation again immediately before boot binding."""
    fixed = (deployment.get("verificationContracts") or {}).get("fixedStaticRoute")
    if fixed is not None:
        generation = fixed.get("dynamicFontGeneration") or {}
        if generation.get("path") != "/data/fonts/config/config.xml" or type(generation.get("exists")) is not bool:
            raise DeploymentError("fixed-static dynamic generation contract missing")
        path = (visible_root / generation["path"].lstrip("/")) if visible_root else Path(generation["path"])
        if path.is_symlink() or path.is_file() != generation["exists"]:
            raise DeploymentError("font update generation appeared or disappeared")
        if path.is_file() and _sha256(path) != generation.get("sha256"):
            raise DeploymentError("font update generation changed before activation")
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


def validate_system_xml_copy_scope(
    deployment: dict[str, Any], payload_root: Path, stock_root: Path,
    source_root: Path | None = None, copy_root: Path | None = None,
) -> None:
    """Prove the two system XML copies against the frozen deployment and ROM.

    This function only reads files. SELinux, private-lower ownership and the
    transaction boundary are checked by the shell before any mount or chcon.
    """
    validate_payload_integrity(deployment, payload_root)
    contract = (deployment.get("verificationContracts") or {}).get("fixedStaticRoute")
    if not isinstance(contract, dict):
        raise DeploymentError("system XML copy requires a sealed fixed-static route")
    snapshot = payload_root / ".luoshu-runtime/deployment/fixed-static-route-plan.json"
    route = _load(snapshot)
    import fixed_static_xml_router
    try:
        fixed_static_xml_router.validate_route_plan(route)
    except (ValueError, KeyError, TypeError, minimal_xml_router.RouterError) as error:
        raise DeploymentError("system XML fixed-static route proof is invalid") from error
    if route.get("routeId") != contract.get("routeId") or route.get("fontPlanId") != deployment.get("fontPlanId"):
        raise DeploymentError("system XML route identity differs from deployment")
    expected_root = payload_root / "system/etc"
    source_root = expected_root if source_root is None else source_root
    if source_root.absolute() != expected_root.absolute():
        raise DeploymentError("system XML source is not the active payload tree")
    for root in (payload_root, source_root, stock_root):
        if root.is_symlink() or not root.is_dir():
            raise DeploymentError("system XML source or stock root is not a regular directory")
    allowed = {"/system/etc/fonts.xml", "/system/etc/font_fallback.xml"}
    files = [item for item in deployment["files"] if item.get("kind") == "xml"]
    if not files or any(item.get("logicalPath") not in allowed for item in files):
        raise DeploymentError("system XML copy scope exceeds the two supported documents")
    names = {Path(item["logicalPath"]).name for item in files}
    for root in (source_root, copy_root):
        if root is None:
            continue
        if root.is_symlink() or not root.is_dir() or {p.name for p in root.iterdir()} != names:
            raise DeploymentError("system XML copy inventory differs from sealed scope")
        if any(p.is_symlink() or not p.is_file() for p in root.iterdir()):
            raise DeploymentError("system XML copy contains a link or non-file")
    for item in files:
        logical = item["logicalPath"]
        name = Path(logical).name
        document = route["documents"].get(logical)
        if (item.get("payloadPath") != "system/etc/" + name or item.get("sourceXml") != logical
                or not isinstance(document, dict) or not document.get("operations")
                or document.get("sourceXml") != logical):
            raise DeploymentError("system XML entry is not bound to its sealed route")
        stock = stock_root / name
        if stock.is_symlink() or not stock.is_file():
            raise DeploymentError("system XML requires the exact regular stock reference")
        if document.get("sourceDigest") != "sha256:" + _sha256(stock):
            raise DeploymentError("system XML stock bytes differ from sealed sourceDigest")
        if copy_root is not None and _sha256(copy_root / name) != item.get("sha256"):
            raise DeploymentError("system XML memory copy differs from sealed payload")


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
        if "fixedStaticRoute" in verification_contracts:
            specs += (("fixedStaticRoute", "routeId", deployment.get("routeId"),
                       ".luoshu-runtime/deployment/fixed-static-route-plan.json"),)
        if set(verification_contracts) != {entry[0] for entry in specs}:
            raise DeploymentError("Deployment contains an unknown verification contract")
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
    parser.add_argument("--validate-device-generation", action="store_true")
    parser.add_argument("--system-xml-stock-root", type=Path)
    parser.add_argument("--system-xml-source-root", type=Path)
    parser.add_argument("--system-xml-copy-root", type=Path)
    parser.add_argument("--visible-root", type=Path)
    parser.add_argument("--expected-deployment-id")
    parser.add_argument("--expected-payload-digest")
    args = parser.parse_args()

    try:
        if args.validate_payload_only is not None:
            deployment = _load(args.validate_payload_only)
            if args.system_xml_stock_root is not None:
                if args.payload_root is None:
                    raise DeploymentError("system XML proof requires payload root")
                validate_system_xml_copy_scope(deployment, args.payload_root, args.system_xml_stock_root,
                                               args.system_xml_source_root, args.system_xml_copy_root)
            else:
                if args.system_xml_source_root is not None or args.system_xml_copy_root is not None:
                    raise DeploymentError("system XML proof requires stock root")
                validate_payload_integrity(deployment, args.payload_root)
            if args.expected_deployment_id is not None and args.expected_deployment_id != deployment.get("deploymentId"):
                raise DeploymentError("运行状态与实际 deploymentId 不一致")
            if args.expected_payload_digest is not None and args.expected_payload_digest != deployment.get("payloadDigest"):
                raise DeploymentError("运行状态与实际 payloadDigest 不一致")
            if args.validate_device_generation:
                validate_device_generation(deployment, args.payload_root)
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
        font_route_contract.validate_route_plan(route_plan, font_plan=font_plan)
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
        print(json.dumps(_error_payload(error, args.artifact_manifest),
                         ensure_ascii=False, separators=(",", ":")))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
