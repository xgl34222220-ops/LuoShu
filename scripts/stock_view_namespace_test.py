#!/usr/bin/env python3
"""Real private Linux mounts and nested scope cancellation, never host mounts.

Android kernel/root-manager behavior remains a separate hardware requirement.
"""
from pathlib import Path
import os, subprocess, sys, tempfile, time, json, shutil
repo=Path(__file__).resolve().parents[1]
if '--inside' not in sys.argv:
 tool=shutil.which('unshare')
 if not tool:
  print('stock_view_namespace_test: SKIP (unshare unavailable)');raise SystemExit(0)
 probe=subprocess.run([tool,'-Urnm','true'],capture_output=True,text=True)
 if probe.returncode:
  if os.environ.get('LUOSHU_REQUIRE_REAL_MOUNT_TEST')=='1':raise RuntimeError(probe.stderr)
  print('stock_view_namespace_test: SKIP (private user/mount namespace unavailable)');raise SystemExit(0)
 raise SystemExit(subprocess.run([tool,'-Urnm',sys.executable,__file__,'--inside']).returncode)
with tempfile.TemporaryDirectory() as raw:
 root=Path(raw);bin=root/'bin';bin.mkdir();ready=root/'ready';owned=root/'owned';source=root/'source';source.mkdir();(source/'Original.ttf').write_text('OEM')
 command=bin/'umount';command.write_text('#!/bin/sh\nsleep 0.8\nexec /usr/bin/umount "$@"\n');command.chmod(0o755)
 worker=root/'worker.py';worker.write_text('import sys,time,subprocess\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(repo/'common'))+')\nimport stock_font_view as v\nwith v.session(Path('+repr(raw)+')) as s:\n s.base=Path('+repr(str(owned))+');s.base.mkdir()\n p=s.base/"system-fonts";p.mkdir();s.owned.append(p)\n subprocess.run(["mount","--bind",'+repr(str(source))+',str(p)],check=True)\n subprocess.run(["mount","-o","remount,bind,ro",str(p)],check=True)\n Path('+repr(str(ready))+').write_text("ready")\n time.sleep(30)\n')
 env=os.environ.copy();env['PATH']=str(bin)+':'+env['PATH']
 p=subprocess.Popen([sys.executable,str(repo/'common/task_scope.py'),'--task','view-cleanup','--timeout','10','--','sh','-c',sys.executable+' '+str(worker)+' & wait'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
 for _ in range(300):
  if ready.exists():break
  if p.poll() is not None:break
  time.sleep(.01)
 assert ready.exists(),p.communicate()
 p.terminate();out,err=p.communicate(timeout=5)
 mounted=str(owned/'system-fonts') in Path('/proc/self/mountinfo').read_text()
 assert p.returncode==143,err
 print(json.dumps({'mount_leaked':mounted,'scope_returncode':p.returncode}))
 if mounted:subprocess.run(['/usr/bin/umount','-l',str(owned/'system-fonts')],check=True)
 assert (source/'Original.ttf').read_text()=='OEM'
 assert not mounted,'cancelled compile left a recovery mount behind'
 assert not owned.exists(),'request directory was not cleaned'
 sys.path.insert(0,str(repo/'common'))
 import stock_font_view as v
 with v.session(root) as second:
  second.base=root/'second';second.base.mkdir()
  target=second.base/'system-fonts';target.mkdir();second.owned.append(target)
  subprocess.run(['mount','--bind',str(source),str(target)],check=True)
  assert (target/'Original.ttf').read_text()=='OEM'
 assert str(target) not in Path('/proc/self/mountinfo').read_text()
 assert not second.base.exists()
 print('stock_view_namespace_test: PASS (real binds, cancellation and second use)')
