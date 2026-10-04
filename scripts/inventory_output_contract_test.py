#!/usr/bin/env python3
"""Exercise actual legacy list router transport, not inventory or mount acceptance."""
import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def run(module, shell):
    source=(module/'common/font_manager.sh').read_text()
    route='case "${1:-}:${2:-}" in'+source.rsplit('case "${1:-}:${2:-}" in',1)[1]
    android=Path('/system/bin/sh').exists()
    row=lambda i:dict(id=f'OwnSynthetic{i:04d}',name='中文 引号 "字体" '+str(i),
                      sample='$(printf injected) ${HOME} `pwd` LUOSHU_MANAGER_OUTPUT',padding='x'*190)
    compact=lambda value:json.dumps(value,ensure_ascii=False,separators=(',',':'))
    small=compact(dict(status='ok',nativeAvailable=False,data=dict(fonts=[row(0)])))
    large=compact(dict(status='ok',nativeAvailable=False,data=dict(fonts=[row(i) for i in range(1000)])))
    failed=compact(dict(status='error',nativeAvailable=False,message='失败 '+('x'*(300*1024))))
    cases=[('small-list',small,0,True),('thousand-row-list',large,0,True),
           ('large-backend-error',failed,7,True),('unavailable-scanner-direct-output',large,0,False),
           ('empty-backend-failure','',7,True)]
    result=dict(schema='luoshu-inventory-output-contract-v1',environment='ANDROID' if android else 'HOST_ONLY',
                tested_scope='CURRENT_LEGACY_LIST_ROUTER_NOT_FULL_INVENTORY_OR_MOUNTS',result='PASS',cases=[])
    with tempfile.TemporaryDirectory(prefix='luoshu-inventory-output-',dir='/data/local/tmp' if android else None) as temp:
        base=Path(temp); data=base/'backend-output'; worker=base/'backend.sh'; script=base/'actual-router.sh'
        worker.write_text('cat "$FIXTURE_OUTPUT"\nexit "$FIXTURE_EXIT"\n')
        prefix=('CURRENT_MANAGER='+shlex.quote(str(worker))+'\n'
                'stock_scan_available() { [ "$FIXTURE_AVAILABLE" = 1 ]; }\n')
        if not android:
            external=shutil.which('printf') or '/usr/bin/printf'
            prefix+='printf() { command '+shlex.quote(external)+' "$@"; }\n'
        script.write_text(prefix+route)
        for name,body,code,available in cases:
            data.write_text(body)
            env=dict(os.environ,FIXTURE_OUTPUT=str(data),FIXTURE_EXIT=str(code),FIXTURE_AVAILABLE=str(int(available)))
            p=subprocess.run([shell,str(script),'action','list'],capture_output=True,text=True,env=env,timeout=30)
            expected=body.replace('"nativeAvailable":false','"nativeAvailable":true') if available else body
            if available:expected+='\n'
            if p.returncode!=code or p.stdout!=expected:
                raise RuntimeError(f'{name}: code={p.returncode}, bytes={len(p.stdout.encode())}, expected_code={code}, expected_bytes={len(expected.encode())}, stderr={p.stderr!r}')
            result['cases'].append(dict(name=name,result='PASS',input_bytes=len(body.encode()),output_bytes=len(p.stdout.encode()),code=code))
    result.update(case_count=len(cases),router_sha256=sha256((module/'common/font_manager.sh').read_bytes()).hexdigest())
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--module',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--shell',default='/system/bin/sh' if Path('/system/bin/sh').exists() else '/bin/sh')
    parser.add_argument('--output',type=Path)
    args=parser.parse_args();result=run(args.module.resolve(),args.shell)
    value=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.write_text(value)
    print(value,end='')
