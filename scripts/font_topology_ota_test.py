#!/usr/bin/env python3
"""Current firmware identity and the trusted refresh boundary."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'common'))
import font_topology_snapshot as topology
import font_inventory as inventory

class OtaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.inv = {'specializedSnapshotRevision':1, 'specializedSnapshots':{}, 'xmlMemberSnapshotRevision':1, 'xmlMemberSnapshots':{}, 'buildKey':'old-build', 'scannerRevision':6, 'slots':{'/system/fonts/A.ttf':{
            'stockIdentity':{'captureRevision':2}, 'stockGeometryProfile':{}}}}
    def test_current_properties_must_match_without_reading_font_bytes(self):
        with patch.object(inventory, 'current_build_key', return_value=('new-build','new-build','display')), \
             patch.object(topology, '_sha256', side_effect=AssertionError('no font hashing')):
            with self.assertRaisesRegex(topology.TopologyError, '构建已变化'):
                topology.validate_inventory_current(self.inv)
        with patch.object(inventory, 'current_build_key', return_value=('old-build','old-build','display')):
            topology.validate_inventory_current(self.inv)
    def test_unknown_current_build_blocks_instead_of_recapturing(self):
        with patch.object(inventory, 'current_build_key', return_value=('unknown','','')):
            with self.assertRaises(topology.CurrentBuildUnavailable):
                topology.validate_inventory_current(self.inv)
    def test_cli_uses_actual_property_command(self):
        inv = self.root/'inventory.json'; inv.write_text(json.dumps(self.inv))
        bin_dir=self.root/'bin';bin_dir.mkdir()
        prop=bin_dir/'getprop';prop.write_text('#!/bin/sh\necho new-build\n');prop.chmod(0o755)
        env={**os.environ, 'PATH':str(bin_dir)+os.pathsep+os.environ.get('PATH','')}
        cmd=[sys.executable,str(ROOT/'common/font_topology_snapshot.py'),'--validate-inventory-current',
             '--inventory',str(inv),'--output',str(self.root/'unused.json')]
        self.assertEqual(subprocess.run(cmd,env=env,capture_output=True).returncode,1)
        self.inv['buildKey']='new-build';inv.write_text(json.dumps(self.inv))
        self.assertEqual(subprocess.run(cmd,env=env,capture_output=True).returncode,0)
    def run_ensure(self, initial, inventory_status):
        module=self.root/'module';common=module/'common';common.mkdir(parents=True)
        (common/'font_manager.sh').write_text('#!/bin/sh\necho "$*" >> "$MODDIR/actions"\n')
        (common/'font_role_shadow.sh').write_text('#!/bin/sh\nexit 0\n')
        shell=(ROOT/'common/font_topology_snapshot.sh').read_text().split('\ncase "${1:-refresh}"',1)[0]
        driver=self.root/'driver.sh'
        driver.write_text(shell+f'''
mkdir -p "$MODDIR/logs"
_topology_exec() {{
    case "$2" in
        --validate-current) [ -f "$MODDIR/refreshed" ] && return 0; return {initial} ;;
        --validate-inventory-current) return {inventory_status} ;;
    esac
    return 1
}}
_topology_refresh() {{ touch "$MODDIR/refreshed"; }}
_topology_ensure
''')
        result=subprocess.run(['sh',str(driver)],env={**os.environ,'MODDIR':str(module)},capture_output=True)
        return result, module
    def test_stale_firmware_forces_stock_scan_before_topology_refresh(self):
        result,module=self.run_ensure(1,1)
        self.assertEqual(result.returncode,0)
        self.assertEqual((module/'actions').read_text().strip(),'action stock_scan')
        self.assertTrue((module/'refreshed').is_file())
    def test_missing_topology_unknown_build_does_not_scan(self):
        result,module=self.run_ensure(1,3)
        self.assertNotEqual(result.returncode,0)
        self.assertFalse((module/'actions').exists())
        self.assertFalse((module/'refreshed').exists())

if __name__=='__main__':unittest.main(verbosity=2)
