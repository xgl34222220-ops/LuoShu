#!/usr/bin/env python3
"""A deployment refusal reaches existing prepare logs with useful bounded causes."""
import contextlib, io, json, sys, tempfile, unittest, subprocess, os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'common'))
import universal_font_deployment as deploy

class BlockedSummaryTests(unittest.TestCase):
    def test_cli_keeps_gate_and_reports_top_causes_and_manifest_inside_tail600(self):
        with tempfile.TemporaryDirectory() as raw:
            root=Path(raw);manifest=root/'b5bfc8cdae9f494fc4b4abe7.json';out=root/'payload'
            data={'summary':{'blockedCount':28},'artifacts':[
              {'status':'blocked','targetPath':'/system/fonts/Skipped.ttf','reason':'skipped-after-atomic-failure:xyz'},
              {'status':'blocked','targetPath':'/system/fonts/MiSansVF.ttf','reason':'static-weight-fallback'},
              {'status':'blocked','targetPath':'/product/fonts/Clock.ttf','reason':'source missing /sdcard/LuoShu/private-font.ttf\n'+'x'*400},
            ]}
            output=io.StringIO()
            with patch.object(sys,'argv',['deployment','--font-plan',str(root/'plan'),'--route-plan',str(root/'route'),'--artifact-manifest',str(manifest),'--payload-root',str(out),'--manifest',str(root/'deployment.json')]), \
                 patch.object(deploy,'_load',side_effect=[{}, {}, data]), \
                 patch.object(deploy.universal_font_plan,'validate_plan'), \
                 patch.object(deploy.minimal_xml_router,'validate_route_plan'), \
                 patch.object(deploy.universal_font_compiler,'validate_manifest'), contextlib.redirect_stdout(output):
                self.assertEqual(deploy.main(),1)
            line=output.getvalue().strip();value=json.loads(line.encode()[-600:].decode())
            self.assertEqual(value['code'],'blocked-artifacts');self.assertIn('blocked=28',value['message'])
            self.assertIn('static-weight-fallback',line);self.assertIn('Clock.ttf',line)
            self.assertIn('config/universal-font-artifact-manifests/'+manifest.name,line)
            self.assertNotIn('private-font',line);self.assertNotIn('skipped-after',line)
            self.assertFalse(out.exists());self.assertLessEqual(len(line.encode()),600)
    def test_line_budget_numbers_survive_the_short_failure_log(self):
        data={'summary':{'blockedCount':77},'artifacts':[{
            'status':'blocked','targetPath':'/system/fonts/MiSansVF.ttf',
            'reason':'fixed composite outlines exceed conservative OEM variable line budget',
            'errorCode':'fixed-line-budget','errorDetails':{'importedYMin':-250,'importedYMax':900,
                                                          'maxDescent':-200,'minAscent':800}},
            *[{'status':'blocked','reason':'skipped-after-atomic-failure:first'} for _ in range(76)]]}
        message=deploy._error_payload(deploy.BlockedArtifactError(data))['message']
        self.assertIn('failed=1',message);self.assertIn('skipped=76',message)
        self.assertIn('bounds=[-250,900] limit=[-200,800]',message)
        self.assertNotIn('skipped-after',message)

    def test_scope_cleanup_cannot_truncate_the_actionable_error(self):
        message=json.dumps({'status':'error','message':'blocked=77; failed=1; MiSansVF.ttf:fixed-line-budget; manifest=config/universal-font-artifact-manifests/example.json'},separators=(',',':'))
        shell=(ROOT/'common/universal_font_cutover.sh').read_text().split('case "${1:-switch}" in',1)[0]
        payload=message+'\n[TASK-CLEANUP] '+json.dumps({'detail':'x'*900})
        with tempfile.TemporaryDirectory() as raw:
            env={**os.environ,'MODDIR':raw,'INPUT':payload}
            result=subprocess.run(['sh','-c',shell+'\n_uc_failure_summary "$INPUT"\n'],env=env,capture_output=True,text=True,check=True)
        self.assertEqual(json.loads(result.stdout),json.loads(message))

    def test_unicode_and_path_text_remain_bounded_and_valid(self):
        data={'summary':{'blockedCount':2},'artifacts':[{'status':'blocked','targetPath':'/system/fonts/'+'字'*100+'.ttf','reason':'坏'*1000+' /private/secret.ttf'}]*2}
        result=deploy._error_payload(deploy.BlockedArtifactError(data),'/private/file.json')
        line=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode()
        self.assertLessEqual(len(line),600);json.loads(line[-600:]);self.assertNotIn(b'secret',line)
        self.assertIn(b'<artifact-manifest>.json',line)
if __name__=='__main__':unittest.main(verbosity=2)
