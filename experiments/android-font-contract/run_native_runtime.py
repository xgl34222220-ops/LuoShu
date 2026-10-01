"""Disposable emulator: execute production Python and lock code as adb shell.

No root, remount, system writes, hidden API settings or module installation.
The x86_64 runtime is a CI-only sibling, not a claim about the ARM64 payload.
"""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,sys,tempfile,time,traceback


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--runtime',type=Path,required=True)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    remote='/data/local/tmp/luoshu-native-runtime';owned=False;report={'state':'running','systemMutation':False,'moduleMountTested':False}
    def adb(*command,timeout=60,check=True):
        start=time.monotonic();result=subprocess.run(['adb',*command],capture_output=True,timeout=timeout)
        with (args.output/'commands.jsonl').open('a') as stream:
            stream.write(json.dumps({'args':command,'returncode':result.returncode,'seconds':round(time.monotonic()-start,3),
                                     'output':(result.stdout+result.stderr).decode(errors='replace')[-2000:]})+'\n')
        if check and result.returncode:raise RuntimeError(str(command)+': '+result.stderr.decode(errors='replace'))
        return result
    try:
        for prop,value in [('ro.kernel.qemu','1'),('ro.build.version.sdk','36'),('ro.product.cpu.abi','x86_64')]:
            if adb('shell','getprop',prop).stdout.decode().strip()!=value:raise RuntimeError('unexpected emulator identity: '+prop)
        if adb('shell','id','-u').stdout.strip()!=b'2000':raise RuntimeError('runtime test requires ordinary adb shell, not root')
        if adb('shell','test','-e',remote,check=False).returncode==0:raise RuntimeError('test runtime path already exists')
        origin=json.loads((args.runtime/'runtime-origin.json').read_text())
        if origin['architecture']!='x86_64' or origin['pythonVersion']!='3.14.6':raise RuntimeError('wrong CI runtime manifest')
        owned=True;adb('push',str(args.runtime),remote,timeout=120)
        adb('push',str(args.source),remote+'/source.ttf')
        adb('push',str(Path(__file__).with_name('native_runtime_smoke.py')),remote+'/smoke.py')
        sdk_font='/system/fonts/NotoSansCJK-Regular.ttc'
        report['fingerprint']=adb('shell','getprop','ro.build.fingerprint').stdout.decode().strip()
        # Compare actual Android measurements to the already native/full-proven
        # host implementation using the SAME freshly captured SDK bytes.
        with tempfile.TemporaryDirectory(prefix='luoshu-native-reference-') as work:
            stock=Path(work)/'stock.ttc';adb('pull',sdk_font,str(stock),timeout=90)
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'common'))
            import universal_font_compiler as compiler
            from fontTools.ttLib import TTFont
            with TTFont(args.source) as source:
                font,location=compiler._stock_geometry_font(stock,0,650,{'wght':650},source_font=source,role='cjk')
                try:
                    expected_profile=compiler._profile_from_font(font);expected=compiler._canonical_hash(expected_profile)
                    (args.output/'host-profile.json').write_text(json.dumps(expected_profile,indent=2))
                finally:font.close()
            stock_sha=hashlib.sha256(stock.read_bytes()).hexdigest()
        py=remote+'/common/python';env=['env','PYTHONUTF8=1','PYTHONHOME='+py,
            'PYTHONPATH='+remote+'/common:'+py+'/lib/python3.14/site-packages',
            'LD_LIBRARY_PATH='+py+'/lib:'+py+'/lib/python3.14/lib-dynload']
        result=adb('shell',*env,py+'/bin/luoshu-python',remote+'/smoke.py','--module',remote,
                   '--source',remote+'/source.ttf','--stock',sdk_font,'--output',remote+'/result.json',timeout=180)
        (args.output/'runtime-stdout.txt').write_bytes(result.stdout)
        observed=json.loads(adb('exec-out','cat',remote+'/result.json').stdout)
        (args.output/'native-result.json').write_text(json.dumps(observed,indent=2))
        if observed.get('state')!='passed' or observed.get('androidPythonExecuted') is not True:raise RuntimeError('native interpreter proof missing')
        probe=observed['actualCff2Probe']
        if probe['stockSha256']!=stock_sha or probe['profileDigest']!=expected or probe['location']!=location:
            raise RuntimeError('actual Android CFF2 profile differs from same-byte host reference')
        report.update(state='passed',runtimeOrigin=origin,native=observed,hostProfileEqual=True)
    except Exception as error:
        report.update(state='failed',error=str(error),trace=traceback.format_exc(limit=12))
    finally:
        if owned:
            try:adb('shell','rm','-rf',remote);report['temporaryRuntimeRemoved']=adb('shell','test','-e',remote,check=False).returncode==1
            except Exception as error:report['cleanupError']=str(error)
        (args.output/'summary.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
    if report['state']!='passed' or report.get('temporaryRuntimeRemoved') is not True:raise SystemExit(1)


if __name__=='__main__':main()
