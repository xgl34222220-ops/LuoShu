"""Schema/privacy negative guards only; no synthetic sample is an Android PASS."""
import copy
import unittest
from inventory_timings import request_timings, verified_timing


def logs():
    return '''I LuoShuStartup: event=font_request_phase stage=fingerprint phase=inventory_detail storage_ms=0.0 snapshot_ms=100.0 cache_ms=0.0 build_ms=0.0 verify_ms=0.0 write_ms=0.0 output_ms=1.0 cache_hit=0 snapshot_count=1 build_count=0 write_count=0 code=0
I LuoShuStartup: event=font_request_phase stage=fingerprint phase=inventory duration_ms=101.5 count=1000 code=0
I LuoShuStartup: event=font_request_phase stage=fingerprint phase=scope duration_ms=5001.5 code=0 cleaned=true reason=success
I LuoShuStartup: event=font_request stage=fingerprint elapsed_ms=6000 duration_ms=5500 code=0'''


class InventoryTimingTests(unittest.TestCase):
    def test_successful_fingerprint_cannot_hide_a_scan_without_subphase_evidence(self):
        incomplete='\n'.join(logs().splitlines()[1:]).replace('stage=fingerprint','stage=scan').replace('elapsed_ms=6000','elapsed_ms=7000')
        records=request_timings(logs()+'\n'+incomplete,0)
        self.assertEqual(2,len(records))
        self.assertFalse(verified_timing(records,0,1000))

    def test_scan_subphases_prove_rebuild_and_cache_reuse_separately(self):
        for hit, builds, writes in [(0,1,2),(1,0,0)]:
            text=logs().replace('stage=fingerprint','stage=scan').replace('snapshot_count=1','snapshot_count=2')
            text=text.replace('snapshot_ms=100.0','snapshot_ms=50.0').replace('verify_ms=0.0','verify_ms=40.0')
            text=text.replace('cache_hit=0',f'cache_hit={hit}').replace('build_count=0',f'build_count={builds}').replace('write_count=0',f'write_count={writes}')
            records=request_timings(text,0)
            self.assertTrue(verified_timing(records,0,1000))
            self.assertEqual(hit,records[0]['phases']['inventory_detail']['cache_hit'])

    def test_missing_or_inconsistent_subphases_cannot_prove_current_work(self):
        original=request_timings(logs(),0)
        for key,value in [('snapshot_ms',102.6),('output_ms',-1),('output_ms',float('inf')),
                          ('cache_hit',1),('snapshot_count',2),('build_count',1),('write_count',1),
                          ('code',False),('snapshot_count',True),('build_count','0')]:
            records=copy.deepcopy(original);records[0]['phases']['inventory_detail'][key]=value
            self.assertFalse(verified_timing(records,0), (key,value))
        del original[0]['phases']['inventory_detail']
        self.assertFalse(verified_timing(original,0))

    def test_subphase_fields_are_exact_and_do_not_borrow_prior_request_work(self):
        for text in [logs().replace('phase=inventory_detail','phase=unknown'),
                     logs().replace('output_ms=1.0','output_ms=1.0 /private/path'),
                     logs().replace('stage=fingerprint phase=inventory_detail','stage=refresh phase=inventory_detail')]:
            self.assertFalse(verified_timing(request_timings(text,0),0))
        text=logs()+'\n'+ '\n'.join(logs().splitlines()[1:]).replace('elapsed_ms=6000','elapsed_ms=7000')
        records=request_timings(text,0)
        self.assertFalse(verified_timing([records[1]],0))
        records=copy.deepcopy(request_timings(logs(),0))
        records[0]['phases']['inventory_detail']['private_path']='secret'
        self.assertFalse(verified_timing(records,0))

    def test_phases_bind_to_completed_live_request(self):
        records=request_timings(logs(), 1000)
        self.assertEqual(1,len(records))
        self.assertEqual(101.5,records[0]['phases']['inventory']['duration_ms'])
        self.assertTrue(verified_timing(records,1000))
        self.assertTrue(verified_timing(records,1000,1000))
        self.assertFalse(verified_timing(records,1000,100))

    def test_older_or_unfinished_records_cannot_prove_current_check(self):
        self.assertEqual([],request_timings(logs(),6001))
        self.assertEqual([],request_timings('\n'.join(logs().splitlines()[:-1]),0))
        self.assertFalse(verified_timing(request_timings(logs(),0),6001))

    def test_timeout_keeps_its_cleanup_state_and_requires_later_success(self):
        timed_out='''event=font_request_phase stage=fingerprint phase=scope duration_ms=8100 code=124 cleaned=true reason=timeout
event=font_request stage=fingerprint elapsed_ms=8200 duration_ms=8200 code=124'''
        records=request_timings(timed_out,0)
        self.assertEqual('timeout',records[0]['phases']['scope']['reason'])
        self.assertFalse(verified_timing(records,0))
        later=logs().replace('elapsed_ms=6000','elapsed_ms=14000')
        self.assertTrue(verified_timing(request_timings(timed_out+'\n'+later,0),0))
        self.assertEqual({},request_timings(timed_out+'\n'+'event=font_request stage=fingerprint elapsed_ms=9000 duration_ms=500 code=0',0)[1]['phases'])

    def test_missing_wrong_action_or_private_text_is_not_phase_evidence(self):
        for text in [logs().replace('phase=scope','phase=unknown'),
                     logs().replace('phase=inventory','phase=unknown'),
                     logs().replace('phase=inventory duration_ms=101.5 count=1000 code=0','phase=inventory duration_ms=101.5 count=1000 code=0 /private/path'),
                     logs().replace('stage=fingerprint phase=inventory','stage=refresh phase=inventory')]:
            self.assertFalse(verified_timing(request_timings(text,0),0))

    def test_unreaped_failure_and_impossible_spans_are_rejected(self):
        original=request_timings(logs(),0)
        for field,value in [('cleaned',False),('code',125),('reason','error'),('duration_ms',-1),('duration_ms',float('inf')),('duration_ms',5502)]:
            records=copy.deepcopy(original);records[0]['phases']['scope'][field]=value
            self.assertFalse(verified_timing(records,0))
        records=copy.deepcopy(original);records[0]['phases']['inventory']['duration_ms']=5003
        self.assertFalse(verified_timing(records,0))
        for target in ('record','inventory','scope'):
            records=copy.deepcopy(original)
            (records[0] if target=='record' else records[0]['phases'][target])['code']=False
            self.assertFalse(verified_timing(records,0))


if __name__=='__main__':
    unittest.main()
