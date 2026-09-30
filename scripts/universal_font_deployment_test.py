#!/usr/bin/env python3
from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "common"))
sys.path.insert(0, str(ROOT / "scripts"))

import font_source_profile
import minimal_xml_router
import universal_font_compiler as compiler
import universal_font_deployment as deployment
import universal_font_plan
import universal_font_compiler_test as fixture


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="luoshu-phase7-") as raw:
        temp = Path(raw)
        source = temp / "User-Regular.ttf"
        stock_xml_font = temp / "Stock-Regular.ttf"
        stock_physical = temp / "Vendor-Regular.ttf"
        stock_dynamic = temp / "Runtime-Regular.ttf"
        fixture.make_font(source, family="User Font", y_min=-90, y_max=710)
        fixture.make_font(stock_xml_font, family="Stock UI", y_min=-100, y_max=720)
        fixture.make_font(stock_physical, family="Vendor UI", y_min=-95, y_max=715)
        fixture.make_font(stock_dynamic, family="Runtime UI", y_min=-100, y_max=720)

        system_xml = temp / "fonts.xml"
        system_xml.write_text(
            '<familyset><family name="sans-serif">'
            '<font weight="400">Stock-Regular.ttf</font>'
            '</family></familyset>',
            encoding="utf-8",
        )

        xml_logical = "/system/fonts/Stock-Regular.ttf"
        physical_logical = "/vendor/fonts/Vendor-Regular.ttf"
        dynamic_logical = "/data/fonts/files/Runtime-Regular.ttf"
        xml_slot = fixture.slot_from_stock(
            xml_logical,
            stock_xml_font,
            family="sans-serif",
            source_xml="/system/etc/fonts.xml",
            declared="Stock-Regular.ttf",
        )
        physical_slot = fixture.slot_from_stock(
            physical_logical,
            stock_physical,
            family="vendor-ui",
            source_xml=None,
            declared="Vendor-Regular.ttf",
        )
        dynamic_slot = fixture.slot_from_stock(
            dynamic_logical,
            stock_dynamic,
            family="runtime-ui",
            source_xml="/data/fonts/config/config.xml",
            declared="Runtime-Regular.ttf",
        )
        dynamic_config = temp / 'dynamic-config.xml'
        dynamic_config.write_text('<fontConfig generation="1"/>')
        dynamic_slot['dynamicIdentity'] = {
            'fontPath': dynamic_logical, 'faceIndex': 0, 'postScriptName': 'RuntimeUI-Regular',
            'fontSha256': hashlib.sha256(stock_dynamic.read_bytes()).hexdigest(),
            'configPath': '/data/fonts/config/config.xml',
            'configSha256': hashlib.sha256(dynamic_config.read_bytes()).hexdigest(),
        }

        profile = font_source_profile.build([source])
        topology = {
            "schema": "device-font-topology-v1",
            "topologyRevision": 3,
            "state": "ready",
            "buildKey": "phase7-test",
            "romKind": "generic",
            "summary": {
                "slotCount": 3,
                "dataFontFileCount": 1,
                "dataFontConfigReferenceCount": 1,
                "unresolvedXmlRefCount": 0,
            },
            "slots": {
                xml_logical: xml_slot,
                physical_logical: physical_slot,
                dynamic_logical: dynamic_slot,
            },
            "families": {},
            "xmlAliases": [],
            "unresolvedXmlRefs": [],
            "runtime": {
                "dataFontFiles": [{"path": dynamic_logical}],
                "dataFontsConfig": {"references": ["Runtime-Regular.ttf"]},
            },
        }
        roles = {
            "schema": "device-font-roles-v1",
            "roleRevision": 3,
            "state": "ready",
            "buildKey": "phase7-test",
            "romKind": "generic",
            "slots": {
                xml_logical: fixture.role_map("latin"),
                physical_logical: fixture.role_map("latin"),
                dynamic_logical: fixture.role_map("latin"),
            },
        }
        font_plan = universal_font_plan.build_plan(topology, roles, profile)
        universal_font_plan.validate_plan(font_plan)

        route_plan = minimal_xml_router.build_route_plan(
            font_plan,
            {"/system/etc/fonts.xml": system_xml},
            None,
            False,
        )
        minimal_xml_router.validate_route_plan(route_plan, font_plan)
        assert route_plan["summary"]["routingComplete"] is True
        assert route_plan["physicalOnlyTargets"] == [physical_logical]
        assert route_plan["deferredDynamicTargets"] == [dynamic_logical]

        def compiler_path(*parts):
            value = Path(*parts)
            return dynamic_config if str(value) == '/data/fonts/config/config.xml' else value
        # Model host access to the sealed logical config without weakening its
        # real-byte digest or the production /data identity contract.
        with patch.object(compiler, 'Path', side_effect=compiler_path):
            artifact_manifest = compiler.compile_all(
                font_plan,
                route_plan,
                {
                    xml_logical: stock_xml_font,
                    physical_logical: stock_physical,
                    dynamic_logical: stock_dynamic,
                },
                temp / "compiled",
                False,
            )
        compiler.validate_manifest(artifact_manifest, font_plan, route_plan)
        assert artifact_manifest["summary"]["blockedCount"] == 0, artifact_manifest
        assert artifact_manifest["summary"]["compiledDynamicTargetCount"] == 1
        assert artifact_manifest["summary"]["deploymentReady"] is True
        assert dynamic_logical in artifact_manifest["dynamicTargetMap"]

        payload_root = temp / "payload"
        manifest = deployment.build_deployment(
            font_plan, route_plan, artifact_manifest, payload_root
        )
        assert Path.cwd().is_dir()
        assert (ROOT / "scripts/universal_font_deployment_bridge_test.sh").is_file()
        deployment.validate_deployment(
            manifest, font_plan, route_plan, artifact_manifest, payload_root
        )
        assert manifest["schema"] == "universal-font-deployment-v1"
        assert manifest["backendNeutral"] is True
        assert manifest["summary"]["activationReady"] is True
        assert manifest["summary"]["backendCount"] == 3
        assert manifest["summary"]["dynamicMountCount"] == 1
        assert manifest["backendProfiles"]["Magisk"]["mountStage"] == "post-fs-data"
        assert manifest["backendProfiles"]["KernelSU"]["mountStage"] == "post-mount"
        assert manifest["backendProfiles"]["APatch"]["mountStage"] == "post-mount"
        assert {
            value["backend"] for value in manifest["backendProfiles"].values()
        } == {"self-mount"}

        file_by_kind = {}
        for item in manifest["files"]:
            file_by_kind.setdefault(item["kind"], []).append(item)
        assert len(file_by_kind["xml"]) == 1
        assert len(file_by_kind["xml-font"]) == 1
        assert len(file_by_kind["physical-font"]) == 1

        rendered_xml = payload_root / "system/etc/fonts.xml"
        assert rendered_xml.is_file()
        rendered = ET.parse(rendered_xml)
        text = (rendered.getroot().find("family/font").text or "").strip()
        assert text.startswith("LuoShu-UF-")
        assert (payload_root / "system/fonts" / text).is_file()
        assert (payload_root / "vendor/fonts/Vendor-Regular.ttf").is_file()

        contracts = manifest["verificationContracts"]
        plan_snapshot = payload_root / contracts["fontPlan"]["payloadPath"]
        artifact_snapshot = payload_root / contracts["artifactManifest"]["payloadPath"]
        assert plan_snapshot.is_file()
        assert artifact_snapshot.is_file()
        assert deployment._sha256(plan_snapshot) == contracts["fontPlan"]["sha256"]
        assert deployment._sha256(artifact_snapshot) == contracts["artifactManifest"]["sha256"]
        assert contracts["fontPlan"]["planId"] == font_plan["planId"]
        assert contracts["artifactManifest"]["manifestId"] == artifact_manifest["manifestId"]

        dynamic = manifest["dynamicMounts"][0]
        assert dynamic["targetPath"] == dynamic_logical
        assert dynamic["readOnly"] is True
        dynamic_source = payload_root / dynamic["sourcePayloadPath"]
        assert dynamic_source.is_file()
        runtime_conf = payload_root / ".luoshu-runtime/deployment/dynamic-mounts.conf"
        assert runtime_conf.is_file()
        assert dynamic_logical in runtime_conf.read_text(encoding="utf-8")

        # Payload identity must not depend on where the prepared directory lives.
        second_root = temp / "payload-elsewhere"
        second = deployment.build_deployment(
            font_plan, route_plan, artifact_manifest, second_root
        )
        assert Path.cwd().is_dir()
        assert (ROOT / ".git").exists() or (ROOT / "scripts").is_dir()
        assert second["payloadDigest"] == manifest["payloadDigest"]
        assert second["deploymentId"] == manifest["deploymentId"]

        # All managers consume one identical payload identity.
        identities = {
            manager: (manifest["payloadDigest"], profile["backend"])
            for manager, profile in manifest["backendProfiles"].items()
        }
        assert len({value[0] for value in identities.values()}) == 1
        assert len({value[1] for value in identities.values()}) == 1

        # Tampering with a frozen verification contract is rejected before next boot.
        original_plan_snapshot = plan_snapshot.read_bytes()
        plan_snapshot.write_bytes(original_plan_snapshot + b" ")
        try:
            deployment.validate_payload_integrity(manifest, payload_root)
        except deployment.DeploymentError as error:
            assert "verification contract" in str(error)
        else:
            raise AssertionError("tampered verification contract unexpectedly validated")
        plan_snapshot.write_bytes(original_plan_snapshot)

        # Tampering with a staged dynamic artifact is rejected before next boot.
        dynamic_source.write_bytes(dynamic_source.read_bytes() + b"x")
        try:
            deployment.validate_payload_integrity(manifest, payload_root)
        except deployment.DeploymentError as error:
            assert "Dynamic mount" in str(error)
        else:
            raise AssertionError("tampered deployment payload unexpectedly validated")

    print("universal_font_deployment_test: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
