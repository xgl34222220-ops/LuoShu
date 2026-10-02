"""Synthetic schema tests only; these fixtures are never Android test reports."""
import copy
import unittest
from verdict import delivery_blockers, preflight_blockers, qualification_blockers, OLD_CASES, REQUEST_CASES, PACKAGE, input_validation_blockers

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
    report = {'run_scope': 'FULL_GATE', 'cycles': [], 'magisk_task_scope': scope(OLD_CASES),
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
                    'first_inventory_frame_ms':1000,'library_open_to_inventory_first_ms':100}
                   for kind in ('app_start','library_open') for i in range(3)]
        report['library_timings'].append({'inventory_count':count,'result':'PASS','samples':samples})
    report['app_apply'] = {'result':'PASS','font_id':'synthetic','task':{'data':{'state':'success','font':'synthetic','task':'new-task','bootId':BOOT['before']}},
                          'reboot':copy.deepcopy(BOOT),'restore_reboot':copy.deepcopy(BOOT),
                          'restore_hashes_equal_stock':True,'mounted':{'font':'synthetic','mount_proofs':{'/system/fonts/a.ttf':{}}},'restore':{'data':{'state':'success'}}}
    identity = {'task': 'new-task', 'boot': BOOT['before'], 'token': 'a'*32}
    source = {'snapshot_digest': 'b'*64, 'source_fingerprint': 'font-selection-v1:' + 'c'*64}
    report['app_apply']['input_events'] = [dict(identity, event='snapshot', **source),
        dict(identity, event='full_validation', valid=True, code=0),
        dict(identity, event='core_entry', source_rechecked=True, **source)]
    return report


class VerdictTests(unittest.TestCase):
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
