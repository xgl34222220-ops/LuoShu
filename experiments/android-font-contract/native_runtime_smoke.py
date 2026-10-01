"""Run production data helpers in an actual Android interpreter, without mounts."""
from pathlib import Path
import argparse,fcntl,hashlib,json,os,platform,subprocess,sys,tempfile,time
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont


def make_master(path,weight):
    builder=FontBuilder(1000,isTTF=True)
    order=['.notdef','A','one','han'];builder.setupGlyphOrder(order)
    builder.setupCharacterMap({65:'A',49:'one',0x4e2d:'han'})
    glyphs={}
    for name in order:
        pen=TTGlyphPen(None)
        if name!='.notdef':
            width=400+weight//10 if name=='A' else 500
            pen.moveTo((50,0));pen.lineTo((width,0));pen.lineTo((width,700));pen.lineTo((50,700));pen.closePath()
        glyphs[name]=pen.glyph()
    builder.setupGlyf(glyphs);builder.setupHorizontalMetrics({n:(700,50) for n in order})
    builder.setupHorizontalHeader(ascent=900,descent=-200)
    builder.setupOS2(sTypoAscender=900,sTypoDescender=-200,usWinAscent=900,usWinDescent=200,usWeightClass=weight)
    builder.setupNameTable({'familyName':'LuoShu Native Runtime','styleName':'Regular','psName':'LuoShuNativeRuntime'})
    builder.setupPost();builder.setupMaxp();builder.save(path)


def variable_data_check(directory):
    import universal_mixed_variable
    import fixed_outline_weight_match
    root=Path(directory);root.mkdir(parents=True,exist_ok=True);masters=[]
    for weight in range(100,901,100):
        path=root/f'{weight}.ttf';make_master(path,weight);masters.append((weight,path))
    result=universal_mixed_variable.build_variable_family(masters,root/'real-variable.ttf')
    if result['variableGlyphCount']<1:raise RuntimeError('native variable builder produced no variation')
    with TTFont(root/'400.ttf',recalcTimestamp=False) as font:
        policy=fixed_outline_weight_match.policy(400);fixed_outline_weight_match.attach(font,policy)
        font.save(root/'fixed-matching.ttf')
    with TTFont(root/'fixed-matching.ttf') as font:
        proof=fixed_outline_weight_match.validate(font,policy)
    return {**{k:result[k] for k in ('state','glyphCount','variableGlyphCount','validatedWeights')},
            'separateConstantMatchingContract':proof}


def lock_check(module):
    module=Path(module);(module/'config').mkdir(exist_ok=True)
    command=['/system/bin/sh','-c','. "$1"; committed() { printf committed; }; luoshu_payload_commit_run "$2" committed',
             'native-lock-test',str(module/'common/payload_commit_lock.sh'),str(module)]
    evidence=[]
    with (module/'config/.payload-commit.flock').open('a') as lock:
        for backend in ('auto','python'):
            env=dict(os.environ,LUOSHU_PAYLOAD_LOCK_BACKEND=backend,LUOSHU_PAYLOAD_LOCK_TIMEOUT='0')
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            busy=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            fcntl.flock(lock,fcntl.LOCK_UN)
            free=subprocess.run(command,env=env,capture_output=True,text=True,timeout=15)
            if busy.returncode==0 or busy.stdout or free.returncode!=0 or free.stdout!='committed':
                raise RuntimeError('native commit lock mismatch: '+repr((backend,busy.returncode,busy.stdout,busy.stderr,free.returncode,free.stdout,free.stderr)))
            evidence.append({'backend':backend,'contentionBlocked':True,'releasedAcquired':True})
    return evidence


def run(module,source,stock):
    if sys.platform!='android' or platform.machine()!='x86_64':raise RuntimeError('not the intended Android x86_64 test runtime')
    if sys.version_info[:3]!=(3,14,6):raise RuntimeError('unexpected Android Python version')
    import fontTools,universal_font_compiler
    if fontTools.__version__!='4.63.0':raise RuntimeError('unexpected FontTools version')
    started=time.monotonic();stock=Path(stock);before=hashlib.sha256(stock.read_bytes()).hexdigest()
    with TTFont(source) as donor:
        font,location=universal_font_compiler._stock_geometry_font(stock,0,650,{'wght':650},source_font=donor,role='cjk')
        try:
            profile=universal_font_compiler._profile_from_font(font)
            glyphs=len(font.getGlyphOrder())
        finally:font.close()
    if before!=hashlib.sha256(stock.read_bytes()).hexdigest():raise RuntimeError('native probe changed OEM bytes')
    probe_seconds=time.monotonic()-started
    with tempfile.TemporaryDirectory(prefix='native-data-',dir=module) as work:
        variable=variable_data_check(work)
    return {'schema':'android-production-runtime-smoke-v1','state':'passed','androidPythonExecuted':True,
            'architecture':platform.machine(),'pythonVersion':sys.version,'fontToolsVersion':fontTools.__version__,
            'pythonBuildApiLevel':sys.getandroidapilevel(),
            'shippedArm64RuntimeExecuted':False,'systemMutation':False,'moduleMountTested':False,
            'actualCff2Probe':{'stockSha256':before,'face':0,'location':location,'glyphCount':glyphs,
                'profileDigest':universal_font_compiler._canonical_hash(profile),'profile':profile,'seconds':round(probe_seconds,3)},
            'actualVariableBuild':variable,'actualMkshCommitLock':lock_check(module)}


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--module',required=True,type=Path)
    parser.add_argument('--source',required=True,type=Path);parser.add_argument('--stock',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    result=run(args.module,args.source,args.stock);args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
