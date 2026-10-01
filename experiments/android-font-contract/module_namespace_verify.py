"""Evidence for real mounts in one disposable Android namespace, not boot proof."""
import hashlib,json,os,sys
from pathlib import Path

def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def verify(module,phase):
 module=Path(module);contract=json.loads((module/'namespace-contract.json').read_text())
 report_path=module/'namespace-result.json'
 report=json.loads(report_path.read_text()) if report_path.exists() else {'scope':'private Android mount namespace','moduleBootTested':False,'rootManagerTested':False,'globalAppConsumerTested':False,'phases':[]}
 payload=module/'.luoshu-payload';manifest=json.loads((payload/'.luoshu-runtime/deployment/deployment.json').read_text())
 new=contract['newAssetPaths']
 first=next(f for f in manifest['files'] if f['logicalPath'] in new)
 asset=payload/first['payloadPath'];hidden=module/'temporarily-hidden-font'
 if phase=='hide-asset':
  assert not hidden.exists();asset.rename(hidden);return
 if phase=='restore-asset':hidden.rename(asset);return
 if phase in ('mounted','idempotent'):
  mounts=[]
  for line in Path('/proc/self/mountinfo').read_text().splitlines():
   fields=line.split();mounts.append((fields[4],fields[5].split(',')))
  for f in manifest['files']:
   logical=f['logicalPath'];assert digest(logical)==f['sha256'],logical
   matching=[row for row in mounts if logical==row[0] or logical.startswith(row[0].rstrip('/')+'/')]
   assert matching and 'ro' in max(matching,key=lambda row:len(row[0]))[1],('not read-only',logical)
  state=(module/'config/universal-font-mount.conf').read_text();assert 'state=mounted\n' in state,state
 else:
  for logical,sha in contract['originalHashes'].items():assert digest(logical)==sha,logical
  for logical in new:assert not Path(logical).exists(),logical
  if phase=='partial-failure':
   calls=[json.loads(line) for line in (module/'mount-calls.jsonl').read_text().splitlines()]
   assert any(c['rc']==0 and c['args'][:3]==['-t','overlay','KSU'] and c['args'][-1]=='/system/etc' for c in calls),'later etc overlay never actually mounted'
   assert not any(c['rc']==0 and c['args'][:2]==['-o','bind'] and c['args'][-1].startswith('/system/') for c in calls),'payload bind occurred before refusal'
  if phase=='integrity-failure':
   assert not (module/'mount-calls.jsonl').read_text(),'integrity failure called mount'
 report['phases'].append({'name':phase,'state':'passed'})
 report['mountNamespace']=os.readlink('/proc/self/ns/mnt');report['initNamespace']=os.readlink('/proc/1/ns/mnt')
 report['state']='passed' if phase=='finished' else 'in-progress'
 report_path.write_text(json.dumps(report,indent=2))
 print(json.dumps({'namespacePhase':phase,'state':'passed'}),flush=True)
if __name__=='__main__':verify(sys.argv[1],sys.argv[2])
