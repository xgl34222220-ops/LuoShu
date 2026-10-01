#!/usr/bin/env python3
"""Real stock scanner seals preserved XML members without adding legacy slots."""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
import font_inventory_scan as scanner
import font_inventory as inventory
import font_topology_snapshot as topology
import font_role_shadow as roles
import font_source_profile as profiles
import universal_font_plan as planner
from universal_font_compiler_test import make_font, make_collection

class MemberTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.fonts=self.root/'fonts';self.etc=self.root/'etc'
        self.fonts.mkdir();self.etc.mkdir()
        make_font(self.fonts/'Ui.ttf',family='UI',variable=True)
        self.serif=self.fonts/'NotoSerifCJK-Regular.ttf';make_font(self.serif,family='Protected Serif')
        self.info=self.root/'mountinfo'
        self.mounts='1 0 0:1 / / rw - tmpfs tmpfs rw\n2 1 253:0 / /system ro - erofs /dev/block/dm-0 ro\n'+f'3 1 253:0 /fonts {self.fonts} ro - erofs /dev/block/dm-0 ro\n'
        self.info.write_text(self.mounts)
        self.check=self.root/'font-check'
        self.check.write_text('#!/bin/sh\necho \'{"valid":true,"format":"TTF","bytes":4096,"variable":false,"color":false}\'\n')
        self.check.chmod(0o755)
    def scan(self,members):
        (self.etc/'fonts.xml').write_text('<familyset><family name="sans-serif"><font>Ui.ttf</font></family><family lang="zh-Hans"><font>Ui.ttf</font>'+members+'</family></familyset>')
        output=self.root/'inventory.json'
        command=[sys.executable,str(ROOT/'common/font_inventory_scan.py'),'--scan','--force','--output',str(output),
            '--system-fonts',str(self.fonts),'--system-etc',str(self.etc),'--build-key','member-fixture','--font-check',str(self.check)]
        env={**os.environ,'LUOSHU_MOUNTINFO':str(self.info),'LUOSHU_DYNAMIC_PARTITION_SCAN_ROOTS':str(self.root/'missing')}
        result=subprocess.run(command,env=env,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'ok')
        data=json.loads(output.read_text())
        candidates=json.loads((self.root/'device_font_candidates.json').read_text())
        tp=topology.build_topology(data,candidates,'',self.root/'absent-config',self.root/'absent-data','')
        rolemap,_=roles.build(tp)
        plan=planner.build_plan(tp,rolemap,profiles.build([self.fonts/'Ui.ttf']))
        return data,tp,plan
    def test_non_xml_clock_has_sealed_specialized_contract(self):
        clock=self.fonts/'AndroidClock.ttf';make_font(clock,family='Android Clock')
        from fontTools.ttLib import TTFont
        from fontTools import subset
        with TTFont(clock) as font:
            sub=subset.Subsetter();sub.populate(text='0123456789');sub.subset(font);font.save(clock)
        self.assertLess(clock.stat().st_size,4096)
        original=self.check.read_text()
        self.check.write_text('#!/bin/sh\ncase "$2" in *AndroidClock.ttf) exec sh '+str(ROOT/'common/font_check.sh')+' "$@" ;; esac\n'+original.split('\n',1)[1])
        data,tp,plan=self.scan('')
        logical='/system/fonts/AndroidClock.ttf'
        self.assertNotIn(logical,data['slots'])
        target=plan['targets'][logical]
        self.assertEqual(target['action'],'compile-specialized')
        contract=target['targetContract']
        self.assertEqual(contract['stockIdentity']['sha256'],hashlib.sha256(clock.read_bytes()).hexdigest())
        self.assertTrue(contract['stockIdentity']['provenance']['verified'])
        self.assertEqual(contract['stockGeometryProfile']['stockSha256'],contract['stockIdentity']['sha256'])
        self.assertTrue(contract['metrics'])

    def test_specialized_snapshot_rejects_overlay_and_requires_cache_upgrade(self):
        clock=self.fonts/'AndroidClock.ttf';make_font(clock,family='Android Clock')
        self.check.write_text('#!/bin/sh\ncase "$2" in *AndroidClock.ttf) exit 1 ;; esac\n'+self.check.read_text().split("\n",1)[1])
        self.info.write_text(self.mounts+f'4 3 253:9 /replacement {clock} ro - ext4 /dev/block/userdata rw\n')
        data,tp,plan=self.scan('')
        logical='/system/fonts/AndroidClock.ttf'
        self.assertEqual(data['specializedSnapshots'][logical]['0']['state'],'unavailable')
        self.assertNotIn('stockIdentity',plan['targets'][logical]['targetContract'])
        old=copy.deepcopy(data);old.pop('specializedSnapshotRevision')
        self.assertFalse(scanner._can_reuse(old,'member-fixture'))
        with patch.object(inventory,'current_build_key',return_value=('member-fixture','','')):
            with self.assertRaisesRegex(topology.TopologyError,'专用物理'):
                topology.validate_inventory_current(old)

    def test_api36_family_preserved_member_has_sealed_contract(self):
        data,tp,plan=self.scan('<font fallbackFor="serif">NotoSerifCJK-Regular.ttf</font>')
        logical='/system/fonts/NotoSerifCJK-Regular.ttf'
        self.assertNotIn(logical,data['slots'])
        member=data['xmlMemberSnapshots'][logical]['0']
        self.assertEqual(member['state'],'ready')
        self.assertEqual(member['stockIdentity']['sha256'],hashlib.sha256(self.serif.read_bytes()).hexdigest())
        self.assertTrue(member['stockIdentity']['provenance']['verified'])
        self.assertEqual(tp['slots'][logical]['faceIndex'],0)
        target=plan['targets'][logical]
        self.assertEqual(target['action'],'preserve')
        self.assertEqual(target['targetContract']['stockIdentity'],member['stockIdentity'])
        self.assertEqual(target['targetContract']['stockIdentities']['0'],member['stockIdentity'])
        self.assertTrue(scanner._can_reuse(data,'member-fixture'))
        with patch.object(inventory,'current_build_key',return_value=('member-fixture','','')):
            topology.validate_inventory_current(data)
            legacy=copy.deepcopy(data);legacy.pop('xmlMemberSnapshotRevision')
            self.assertFalse(scanner._can_reuse(legacy,'member-fixture'))
            with self.assertRaisesRegex(topology.TopologyError,'XML'):
                topology.validate_inventory_current(legacy)
            partial=copy.deepcopy(data);partial['xmlMemberSnapshots'][logical].pop('0')
            self.assertFalse(scanner.has_xml_member_snapshots(partial))
    def test_collection_members_bind_each_face_without_selecting_first(self):
        collection=self.fonts/'NotoSerifCJK-Regular.ttc'
        make_collection(collection,self.fonts/'Ui.ttf',self.serif)
        data,tp,plan=self.scan('<font fallbackFor="serif" index="0">NotoSerifCJK-Regular.ttc</font><font fallbackFor="serif" index="1">NotoSerifCJK-Regular.ttc</font>')
        logical='/system/fonts/NotoSerifCJK-Regular.ttc'
        self.assertNotIn(logical,data['slots'])
        self.assertEqual(set(tp['slots'][logical]['stockIdentities']),{'0','1'})
        self.assertNotIn('stockIdentity',tp['slots'][logical])
        self.assertEqual(plan['targets'][logical]['action'],'preserve')
        identities=plan['targets'][logical]['targetContract']['stockIdentities']
        self.assertEqual(identities['1']['faceIndex'],1)
        self.assertEqual(identities['0']['sha256'],identities['1']['sha256'])
    def test_bad_face_is_explicit_unavailable_without_poisoning_legacy(self):
        data,tp,plan=self.scan('<font fallbackFor="serif" index="4">NotoSerifCJK-Regular.ttf</font>')
        logical='/system/fonts/NotoSerifCJK-Regular.ttf'
        member=data['xmlMemberSnapshots'][logical]['4']
        self.assertEqual(member['state'],'unavailable')
        self.assertIn('face index',member['reason'])
        self.assertNotIn('stockIdentity',tp['slots'][logical])
        self.assertEqual(plan['targets'][logical]['action'],'preserve')
        self.assertTrue(scanner.has_xml_member_snapshots(data))
    def test_overlaid_member_never_becomes_verified(self):
        self.info.write_text(self.mounts+f'4 3 253:9 /replacement {self.serif} ro - ext4 /dev/block/userdata rw\n')
        data,tp,plan=self.scan('<font fallbackFor="serif">NotoSerifCJK-Regular.ttf</font>')
        logical='/system/fonts/NotoSerifCJK-Regular.ttf'
        member=data['xmlMemberSnapshots'][logical]['0']
        self.assertEqual(member['state'],'unavailable')
        self.assertIn('lineage-mismatch',member['reason'])
        self.assertNotIn(logical,data['slots'])
        self.assertNotIn('stockIdentity',tp['slots'][logical])
        self.assertEqual(plan['targets'][logical]['action'],'preserve')

if __name__=='__main__':unittest.main(verbosity=2)
