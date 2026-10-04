"""Synthetic schema tests only; these fixtures are never Android test reports."""
import copy
import unittest
from test_composite_gate import valid_composite
from verdict import delivery_blockers, preflight_blockers, qualification_blockers, OLD_CASES, REQUEST_CASES, PACKAGE, input_validation_blockers, MIX_HANDOFF_CASES, PREVIEW_SOURCE_CASES, COMPOSITE_ERROR_CASES

BOOT = {'before': '11111111-1111-1111-1111-111111111111', 'after': '22222222-2222-2222-2222-222222222222'}


def scope(expected, request=False):
    cases = []
    record = {'pid':12,'start':1,'boot':BOOT['before'],'token':'a'*32}
    for mode, code in expected.items():
        cases.append({'mode': mode, 'result': 'PASS', 'supervisor_exit': code,
                      'late_fork':dict(record),'sentinel':dict(record,pid=13),
                      'identities':[dict(record,pid=20+i) for i in range(5)],
                      **{k:dict(record,pid=30+i) for i,k in enumerate(('supervisor','worker','owned_leaf','double_fork_intermediate'))},
                      'immediate_cleanup': {'token_members': [], 'recorded_alive_including_zombies': [], 'scope_directory_entries': []},
                      'delayed_cleanup': {'token_members': [], 'recorded_alive_including_zombies': [], 'scope_directory_entries': []},
                      'terminal_state': {'state': 'success' if mode == 'success' else 'failed'},
                      'finished': {'cleaned': True}, 'scope_entries_after': [],
                      'worker_stdin': {'is_devnull': True, 'private_fd_not_inherited': True}})
    for case in cases:
        if case['mode'] == 'writer_death':
            case['client_writer']={'pid':99,'start':1,'boot':BOOT['before']}
            case['client_writer_exit']=-9
            case['identities'].append(case['client_writer'])
    return {'result': 'PASS', 'selinux': 'Enforcing', 'cases': cases, 'environment': 'ACTUAL_ANDROID_QEMU_ROOT_ENFORCING'}


def valid_delivery():
    report = {'legacy_composite': valid_composite(), 'run_scope': 'FULL_GATE', 'cycles': [], 'magisk_task_scope': scope(OLD_CASES),
              'magisk_request_scope': scope(REQUEST_CASES, True),
              'app_root': 'PROVEN_BY_ACTUAL_APP_VERIFIED_ROOT_LIBRARY', 'library_timings': [],
              'candidate_apk_sha256': 'b'*64, 'fixture_inventory': [{'files':n,'unique_content_hashes':['c'*64,'d'*64]} for n in (100,1000)],
              'root_policy': {'package': PACKAGE, 'uid': 10123}, 'root_policy_revoked': True,
              'upgrade': {'result': 'PASS'}, 'final_ui': {'result': 'PASS', 'target_fatal': False, 'anr': False},
              'final_workspace': {'result': 'PASS', 'entries': []}}
    for label in ('baseline', 'candidate'):
        report['cycles'].append({'label': label, 'result': 'PASS', 'zip_sha256': 'a'*64,
            **{k:copy.deepcopy(BOOT) for k in ('install_reboot','font_reboot','switch_b_reboot','restore_reboot')},
            'restore_hashes_equal_stock': True,
            'mounted_a': {'font': 'a', 'changed': ['/system/fonts/a.ttf'], 'mount_proofs': {'/system/fonts/a.ttf': {'canonical':'/system/fonts/a.ttf','mount_records':[['actual-proof']]}}},
            'mounted_b': {'font': 'b', 'changed': ['/system/fonts/a.ttf'], 'mount_proofs': {'/system/fonts/a.ttf': {'canonical':'/system/fonts/a.ttf','mount_records':[['actual-proof']]}}},
            'invalid_switch': {'data': {'state': 'failed'}}, 'prepare_failure_crashes': '',
            'commit_failure': {'data': {'state': 'failed'}, 'injection_hit': 'exact synthetic marker', 'reboot': copy.deepcopy(BOOT), 'crash_buffer': ''}})
    for count in (100,1000):
        samples = [{'kind': kind,'repetition': i,'count':count,'verified':True,'pid':'123','target_fatal':False,'anr':False,
                    'first_inventory_frame_ms':1000,'library_open_to_inventory_first_ms':100,
                    'start_ms':1,'request_timings':[{'stage':'fingerprint','completed_at_ms':100,'duration_ms':20,'code':0,
                        'phases':{'inventory':{'duration_ms':2,'count':count,'code':0},
                                  'scope':{'duration_ms':10,'code':0,'cleaned':True,'reason':'success'}}}]}
                   for kind in ('app_start','library_open') for i in range(3)]
        report['library_timings'].append({'inventory_count':count,'result':'PASS','samples':samples})
    report['final_ui']['observations']={'samples':copy.deepcopy([s for s in samples if s['repetition']==0])}
    report['app_apply'] = {'result':'PASS','font_id':'synthetic','task':{'data':{'state':'success','font':'synthetic','task':'new-task','bootId':BOOT['before']}},
                          'reboot':copy.deepcopy(BOOT),'restore_reboot':copy.deepcopy(BOOT),
                          'restore_hashes_equal_stock':True,'mounted':{'font':'synthetic','mount_proofs':{'/system/fonts/a.ttf':{}}},'restore':{'data':{'state':'success'}}}
    identity = {'task': 'new-task', 'boot': BOOT['before'], 'token': 'a'*32}
    report['magisk_mix_handoff'] = {
        'schema': 'luoshu-mix-handoff-contract-v1', 'result': 'PASS', 'environment': 'ANDROID',
        'selinux': 'Enforcing', 'boot_id': BOOT['before'], 'module': '/data/adb/modules/LuoShu',
        'shell': '/system/bin/sh', 'case_count': len(MIX_HANDOFF_CASES),
        'cases': [{'name': name, 'result': 'PASS'} for name in sorted(MIX_HANDOFF_CASES)],
    }
    report['magisk_preview_source'] = {
        'schema': 'luoshu-preview-source-contract-v1', 'result': 'PASS', 'environment': 'ANDROID',
        'selinux': 'Enforcing', 'boot_id': BOOT['before'], 'module': '/data/adb/modules/LuoShu',
        'shell': '/system/bin/sh', 'case_count': len(PREVIEW_SOURCE_CASES),
        'cases': [{'name': name, 'result': 'PASS'} for name in sorted(PREVIEW_SOURCE_CASES)],
    }
    report['magisk_composite_error'] = {
        'schema': 'luoshu-composite-error-contract-v1', 'result': 'PASS', 'environment': 'ANDROID',
        'selinux': 'Enforcing', 'boot_id': BOOT['before'], 'module': '/data/adb/modules/LuoShu',
        'shell': '/system/bin/sh', 'case_count': len(COMPOSITE_ERROR_CASES),
        'cases': [{'name': name, 'result': 'PASS'} for name in sorted(COMPOSITE_ERROR_CASES)],
    }
    weight = {'tag': 'wght', 'name': 'Weight', 'min': 400, 'default': 400, 'max': 900, 'hidden': False}
    report['axis_metadata'] = {'status': 'ok', 'variable': True, 'hasWeight': True, 'weight': weight, 'axes': [weight]}
    report['app_axes'] = {'result': 'PASS', 'package': PACKAGE, 'font_id': 'LuoShuAxisGate',
        'actual_app_pid': '123', 'source_sha256': 'e'*64, 'stock_hashes_unchanged': True,
        'imported_sha256': 'e'*64, 'import_result': {'status': 'ok', 'data': {'kind': 'font',
            'id': 'LuoShuAxisGate', 'supportsCjk': True, 'duplicate': False}},
        'target_fatal': False, 'anr': False, 'hidden_axis_visible': False, 'cjk_card_scanned_to_next_slot': True,
        'next_slot_detail_bounds': '[0,150][200,190]',
        'observed_labels': ['字宽', '纹理细节', 'XTRA', '可变字体', '英文字形']}
    source = {'snapshot_digest': 'b'*64, 'source_fingerprint': 'font-selection-v1:' + 'c'*64}
    report['app_apply']['input_events'] = [dict(identity, event='snapshot', **source),
        dict(identity, event='full_validation', valid=True, code=0),
        dict(identity, event='core_entry', source_rechecked=True, **source)]
    return report


class VerdictTests(unittest.TestCase):
    def test_inventory_timing_presence_cannot_be_claimed_by_a_boolean(self):
        r=valid_delivery()
        r['library_timings'][0]['samples'][0]['request_timings']=True
        self.assertTrue(any('request phase timings' in e for e in delivery_blockers(r)))
        r=valid_delivery()
        del r['final_ui']['observations']
        self.assertTrue(any('final cold/warm live request' in e for e in delivery_blockers(r)))

    def test_app_input_chain_requires_exact_order_and_identity(self):
        for mutation in ('order', 'task', 'boot', 'token', 'digest', 'valid', 'rechecked'):
            report = valid_delivery()
            events = report['app_apply']['input_events']
            if mutation == 'order': events.reverse()
            elif mutation in ('task', 'boot', 'token'): events[1][mutation] = 'wrong'
            elif mutation == 'digest': events[2]['snapshot_digest'] = 'd'*64
            elif mutation == 'valid': events[1]['valid'] = False
            else: events[2]['source_rechecked'] = False
            self.assertTrue(delivery_blockers(report), mutation)

    def test_complete_schema(self):
        self.assertEqual(delivery_blockers(valid_delivery()), [])

    def test_host_missing_duplicate_or_failed_handoff_cases_cannot_pass_android(self):
        for mutation in ('host', 'missing', 'duplicate', 'failed'):
            with self.subTest(mutation=mutation):
                r = valid_delivery(); value = r['magisk_mix_handoff']
                if mutation == 'host': value['environment'] = 'HOST_ONLY'
                elif mutation == 'missing': value['cases'].pop()
                elif mutation == 'duplicate': value['cases'][0] = value['cases'][1].copy()
                else: value['cases'][0]['result'] = 'FAIL'
                self.assertTrue(delivery_blockers(r))

    def test_handoff_context_must_remain_the_exact_enforcing_module(self):
        for key, value in (('boot_id', ''), ('selinux', 'Permissive'), ('module', '/data/adb/modules/LuoShu-copy')):
            r = valid_delivery(); r['magisk_mix_handoff'][key] = value
            self.assertTrue(delivery_blockers(r))

    def test_preview_source_requires_all_actual_android_selection_cases(self):
        for mutation in ('host', 'missing', 'duplicate', 'failed', 'malformed'):
            with self.subTest(mutation=mutation):
                r = valid_delivery(); value = r['magisk_preview_source']
                if mutation == 'host': value['environment'] = 'HOST_ONLY'
                elif mutation == 'missing': value['cases'].pop()
                elif mutation == 'duplicate': value['cases'][0] = value['cases'][1].copy()
                elif mutation == 'failed': value['cases'][0]['result'] = 'FAIL'
                else: value['cases'][0] = None
                self.assertTrue(delivery_blockers(r))

    def test_preview_selection_requires_original_enforcing_module_context(self):
        for key, value in (('boot_id', ''), ('selinux', 'Permissive'),
                           ('module', '/data/local/tmp/fixture'), ('shell', 'sh')):
            r = valid_delivery(); r['magisk_preview_source'][key] = value
            self.assertTrue(delivery_blockers(r))

    def test_composite_error_requires_actual_android_complete_case_set(self):
        for mutation in ('host', 'missing', 'duplicate', 'failed', 'malformed'):
            with self.subTest(mutation=mutation):
                r = valid_delivery(); value = r['magisk_composite_error']
                if mutation == 'host': value['environment'] = 'HOST_ONLY'
                elif mutation == 'missing': value['cases'].pop()
                elif mutation == 'duplicate': value['cases'][0] = value['cases'][1].copy()
                elif mutation == 'failed': value['cases'][0]['result'] = 'FAIL'
                else: value['cases'][0] = None
                self.assertTrue(delivery_blockers(r))

    def test_composite_error_requires_installed_module_and_enforcing_boot(self):
        for key, value in (('boot_id', ''), ('selinux', 'Permissive'),
                           ('module', '/data/local/tmp/fixture'), ('shell', 'sh')):
            r = valid_delivery(); r['magisk_composite_error'][key] = value
            self.assertTrue(delivery_blockers(r))

    def test_actual_collection_axis_name_flags_and_bounds_are_required(self):
        for key, value in (('name', ''), ('hidden', True), ('default', 450), ('tag', 'wdth')):
            r = valid_delivery(); r['axis_metadata']['weight'][key] = value
            self.assertTrue(delivery_blockers(r))

    def test_axis_ui_pass_requires_visible_names_complete_card_and_no_mount_changes(self):
        for mutation in ('label', 'hidden', 'stock', 'card'):
            r = valid_delivery(); value = r['app_axes']
            if mutation == 'label': value['observed_labels'].remove('纹理细节')
            elif mutation == 'hidden': value['observed_labels'].append('HIDN')
            elif mutation == 'stock': value['stock_hashes_unchanged'] = False
            else: value['cjk_card_scanned_to_next_slot'] = False
            self.assertTrue(delivery_blockers(r))

    def test_axis_ui_requires_a_real_new_import_with_exact_source_bytes(self):
        for mutation in ('missing', 'duplicate', 'id', 'hash', 'unsupported'):
            with self.subTest(mutation=mutation):
                r = valid_delivery(); value = r['app_axes']
                if mutation == 'missing': value.pop('import_result')
                elif mutation == 'hash': value['imported_sha256'] = 'f'*64
                else:
                    data = value['import_result']['data']
                    if mutation == 'duplicate': data['duplicate'] = True
                    elif mutation == 'id': data['id'] = 'other-font'
                    else: data['supportsCjk'] = False
                self.assertTrue(delivery_blockers(r))

    def test_card_scan_requires_actual_detail_heading_coordinates(self):
        for invalid in ('', 'summary-only', '[0,0][0,0]extra'):
            r = valid_delivery(); r['app_axes']['next_slot_detail_bounds'] = invalid
            self.assertTrue(delivery_blockers(r))
    def test_diagnostic_fake_pass_blocked(self):
        r=valid_delivery();r.update(run_scope='APP_DIAGNOSTIC_ONLY',delivery_gate='PASS')
        self.assertTrue(delivery_blockers(r))
    def test_missing_each_top_level_field_blocks(self):
        for key in valid_delivery():
            with self.subTest(key=key):
                r=valid_delivery();del r[key];self.assertTrue(delivery_blockers(r))
    def test_failed_scope_and_late_live_process_block(self):
        for change in ('status','member','case'):
            r=valid_delivery();v=r['magisk_request_scope']
            if change=='status':v['result']='FAIL'
            elif change=='member':v['cases'][0]['delayed_cleanup']['token_members']=[123]
            else:v['cases'].pop()
            self.assertTrue(delivery_blockers(r))
    def test_empty_frame_is_not_inventory_evidence(self):
        r=valid_delivery();s=r['library_timings'][0]['samples'][0];del s['first_inventory_frame_ms'];s['first_frame_count']=0
        self.assertTrue(delivery_blockers(r))
    def test_native_crash_blocks_candidate_but_preserves_baseline_history(self):
        r=valid_delivery();r['cycles'][0]['commit_failure']['crash_buffer']='baseline original sed SIGSEGV'
        self.assertEqual(delivery_blockers(r),[])
        r['cycles'][1]['commit_failure']['crash_buffer']='candidate SIGSEGV'
        self.assertTrue(delivery_blockers(r))
    def test_final_fatal_anr_or_policy_failure_blocks(self):
        for key in ('target_fatal','anr'):
            r=valid_delivery();r['final_ui'][key]=True;self.assertTrue(delivery_blockers(r))
        r=valid_delivery();r['root_policy_revoked']=False;self.assertTrue(delivery_blockers(r))
    def test_malformed_is_fail_closed(self):
        for value in (None,[],{'cycles':None}):
            self.assertTrue(delivery_blockers(value))
            self.assertTrue(preflight_blockers(value))
            self.assertTrue(qualification_blockers(value))
    def test_preflight_blocked_is_not_exit_code_failure(self):
        r={'selinux':'Enforcing','delivery_gate':'BLOCKED','checks':{'candidate_official_composite_entry':{'result':'PASS','exit':0},'candidate_scope':scope(OLD_CASES),'app_launch_only':{'result':'BLOCKED','reason':'System UI ANR recorded'}}}
        self.assertEqual(preflight_blockers(r),[])
        r['checks']['app_launch_only']={'result':'FAIL','reason':'target FATAL'}
        self.assertTrue(preflight_blockers(r))
