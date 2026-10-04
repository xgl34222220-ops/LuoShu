"""Synthetic negative evidence only; never a claim of Android App execution."""
import copy
from hashlib import sha256
import json
import struct
import unittest
import xml.etree.ElementTree as ET
import zlib
from app_composite_gate import ENTRY, SLOTS, app_composite_blockers, selected_slot, unique_target, verify_ui_artifact
from app_library_gate import PACKAGE
from composite_gate import run
from test_composite_gate import valid_composite


def node(text='', **attrs):
    return ET.Element('node', dict(package=PACKAGE, text=text, enabled='true', bounds='[0,0][200,200]', **attrs))


def choice_tree(title, name):
    tree = ET.Element('hierarchy')
    tile = node(clickable='true'); tile.extend([node(title),node(name)]); tree.append(tile)
    return tree


def valid_app_composite():
    report = valid_composite(); report['entry'] = ENTRY
    report['task']['data']['message'] = '新组合已准备，重启后生效'
    report['axes_task'].update({k + 'Axes': 'wght=400' for k in SLOTS})
    report['ui'] = dict(result='PASS', package=PACKAGE, action='生成并应用',
                       target_fatal=False, anr=False, pid='123', completed_pid='123',
                       admitted_task='axes-1', old_task='axes-old', boot_id=report['reboot']['before'],
                       admitted_state=dict(report['sources'],task='axes-1'),
                       selected={k:dict(id=v,name=v,frame=f'frame-{i:03d}.xml') for i,(k,v) in enumerate(report['sources'].items())},
                       action_frame='frame-003.xml', completed_frame='frame-004.xml',
                       completed_screenshot='completed.png', completed_message=report['task']['data']['message'])
    return report


def raw_fixture(report):
    ui = report['ui']; files = {}
    for k, title in SLOTS.items():
        files[ui['selected'][k]['frame']] = ET.tostring(choice_tree(title, ui['selected'][k]['name']))
    tree = ET.Element('hierarchy'); tree.append(node('生成并应用', clickable='true'))
    files[ui['action_frame']] = ET.tostring(tree)
    tree = ET.Element('hierarchy')
    tree.extend([node('组合字体已生成'),node(ui['completed_message']),node('100%')])
    files[ui['completed_frame']] = ET.tostring(tree)
    def chunk(kind, data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    image = (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,2,0,0,0))
             +chunk(b'tEXt',b'Scope\0SYNTHETIC HOST NEGATIVE GUARD FIXTURE')
             +chunk(b'IDAT',zlib.compress(b'\0\0\0\0'))+chunk(b'IEND',b''))
    files['completed.png'] = image; ui['completed_screenshot_sha256'] = sha256(image).hexdigest()
    commands = [dict(argv=['shell','input','tap','10','10'],exit=0,stdout='') for _ in range(8)]
    commands += [dict(argv=['shell','pidof',PACKAGE],exit=0,stdout='123\n') for _ in range(2)]
    files['commands.jsonl'] = '\n'.join(json.dumps(c) for c in commands).encode()
    return files


class AppCompositeGateTests(unittest.TestCase):
    def test_raw_evidence_complete_fixture_and_missing_guard(self):
        report=valid_app_composite(); files=raw_fixture(report)
        self.assertEqual(app_composite_blockers(report),[])
        self.assertEqual(verify_ui_artifact(report,files.__getitem__),[])
        for key in report['ui']:
            changed=copy.deepcopy(report);del changed['ui'][key]
            self.assertTrue(app_composite_blockers(changed) or verify_ui_artifact(changed,files.__getitem__),key)

    def test_cli_composite_does_not_satisfy_actual_app_entry(self):
        self.assertTrue(app_composite_blockers(valid_composite()))
        report=valid_app_composite();report['ui']['action']='直接应用此字体'
        self.assertTrue(app_composite_blockers(report))

    def test_wrong_slot_or_page_level_font_name_is_rejected(self):
        tree=choice_tree('中文基底','actual-a');tree.append(node('expected-a'))
        with self.assertRaises(ValueError):selected_slot(tree,'中文基底','expected-a')
        with self.assertRaises(ValueError):selected_slot(tree,'英文字形','actual-a')

    def test_wrong_package_disabled_and_duplicate_targets_are_rejected(self):
        for change in ('package','enabled','duplicate'):
            tree=choice_tree('中文基底','a')
            if change=='package':
                for n in tree.iter('node'):n.set('package','unrelated.package')
            elif change=='enabled':tree[0].set('enabled','false')
            else:tree.append(copy.deepcopy(tree[0]))
            with self.assertRaises(ValueError):unique_target(tree,'中文基底')

    def test_reused_task_different_boot_pid_and_source_fail(self):
        for key,value in [('admitted_task','axes-old'),('old_task','axes-1'),('boot_id','other-boot'),('completed_pid','456')]:
            report=valid_app_composite();report['ui'][key]=value
            self.assertTrue(app_composite_blockers(report),key)
        report=valid_app_composite();report['ui']['selected']['latin']['id']='other-font'
        self.assertTrue(app_composite_blockers(report))

    def test_raw_action_completion_or_pid_drift_is_rejected(self):
        for change in ('direct-action','success-title-only','pid'):
            report=valid_app_composite();files=raw_fixture(report)
            if change=='direct-action':
                tree=ET.fromstring(files['frame-003.xml']);tree[0].set('text','直接应用此字体')
                files['frame-003.xml']=ET.tostring(tree)
            elif change=='success-title-only':
                files['frame-004.xml']=ET.tostring(choice_tree('组合字体已生成','an unrelated old message'))
            else:report['ui']['pid']=report['ui']['completed_pid']='456'
            self.assertTrue(verify_ui_artifact(report,files.__getitem__),change)

    def test_cli_rescue_or_unowned_frame_cannot_substitute(self):
        report=valid_app_composite();files=raw_fixture(report)
        files['commands.jsonl']+=b'\n'+json.dumps(dict(argv=['shell','sh app_bridge.sh mix_start a b b'],exit=0)).encode()
        self.assertTrue(verify_ui_artifact(report,files.__getitem__))
        report=valid_app_composite();files=raw_fixture(report);report['ui']['action_frame']='../other-stage.xml'
        self.assertTrue(verify_ui_artifact(report,files.__getitem__))

    def test_failed_actual_ui_admission_has_no_cli_fallback(self):
        calls=[]
        def root(body,**kwargs):
            calls.append(body)
            return json.dumps(valid_composite()['commit_lock_probe']) if body.startswith('cat ') else ''
        def failed_ui(sources):
            raise RuntimeError('actual UI did not admit task')
        with self.assertRaisesRegex(RuntimeError,'actual UI did not admit'):
            run({},'/module',root,lambda *a:None,lambda:None,lambda:{},
                lambda *a:None,lambda *a:None,{},['a','b'],'.',app_admit=failed_ui)
        self.assertFalse(any('font_mix_controller.sh' in c or 'mix_start' in c for c in calls))


if __name__=='__main__':
    unittest.main()
