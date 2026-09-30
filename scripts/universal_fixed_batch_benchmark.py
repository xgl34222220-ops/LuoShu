#!/usr/bin/env python3
"""Reproducible synthetic fixed-composite batch; no device/user font inputs.

Full comparisons (slow, optional; no timing assertion):
  python scripts/universal_fixed_batch_benchmark.py --han 20000 --contours 48 --mode both --output-dir /tmp/luoshu-20k
  python scripts/universal_fixed_batch_benchmark.py --han 35000 --contours 48 --mode optimized --output-dir /tmp/luoshu-35k
Small correctness run: --han 6000 --contours 1 --smoke --mode both

The 35-unit layout has 1 UI asset/6 references, 4 CJK assets/5 references,
17 Latin assets/23 references, and 1 clock asset/reference. Synthetic stock
origin is explicitly mocked at the kernel-proof seam; this does NOT test or
claim real OEM provenance, Android speed, or successful deployment.
"""
from pathlib import Path
from copy import deepcopy
from unittest.mock import patch
import argparse
import hashlib
import json
import resource
import sys
import tempfile
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.fontBuilder import FontBuilder
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
import universal_font_compiler as compiler
import universal_font_compiler_test as fixture
import universal_mixed_performance_test as generator
import device_font_slot_build_base as slot_build


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def variable_copy(source,output):
    with TTFont(source) as font:
        builder=FontBuilder(font=font)
        builder.setupFvar([('wght',100,400,900,'Weight')],[])
        variations={}
        for name in font.getGlyphOrder():
            count=len(font['glyf'][name].getCoordinates(font['glyf'])[0])
            variations[name]=[TupleVariation({'wght':(0,1,1)},[(2,0)]*count+[(0,0)]*4)]
        builder.setupGvar(variations);font.save(output)


def run(root,han,contours,mode,smoke):
    root.mkdir(parents=True,exist_ok=True)
    source=root/'source.ttf';big=root/'large-vf.ttf';small=root/'small.ttf';small_vf=root/'small-vf.ttf'
    if not source.exists():generator.make_cjk_font(source,han,contours)
    if not small.exists():fixture.make_font(small,family='Synthetic Small')
    if not big.exists():variable_copy(source,big)
    if not small_vf.exists():variable_copy(small,small_vf)
    with TTFont(source,lazy=True) as font:
        actual_han=sum(slot_build.is_cjk(cp) for cp in font.getBestCmap())
    if actual_han < han:raise AssertionError('requested Han count must not include non-Han codepoints')
    bases={}
    for kind,stock,role in [('ui',big,'ui-sans'),('cjk-vf',big,'cjk'),('cjk-static',source,'cjk'),
                            ('latin-vf',small_vf,'latin'),('latin-static',small,'latin'),('clock',small,'clock')]:
        logical=f'/system/fonts/Synthetic-{kind}.ttf'
        slot=fixture.slot_from_stock(logical,stock,family='sans-serif',source_xml=None,declared=Path(logical).name)
        plan,_=fixture.build_plans(source,slot,role,None);target=plan['targets'][logical]
        target['source']['mixedSelection']={'policy':'fixed-composite-selection-v1','requestId':'synthetic-benchmark',
            'fontSha256':digest(source),'roles':{r:{'mode':'fixed','selectedAxes':{'wght':400}} for r in ('cjk','latin','digit')}}
        bases[kind]=(target,plan,stock)
    sequence=['ui']*6+['cjk-vf']*2+['cjk-static']*3+['latin-vf']*8+['latin-static']*15+['clock']
    if smoke:sequence=sequence[:2]
    cases=[]
    for i,kind in enumerate(sequence):
        target,plan,original=bases[kind];target=deepcopy(target)
        asset=(f'cjk-static-{i-8}' if kind=='cjk-static' else f'latin-vf-{min((i-11)//3,2)}' if kind=='latin-vf'
               else f'latin-static-{min(i-19,13)}' if kind=='latin-static' else kind)
        stock=root/('asset-'+asset+'.ttf')
        if not stock.exists():
            with TTFont(original,lazy=True,recalcTimestamp=False,recalcBBoxes=False) as font:
                for nameid in (1,4,6):font['name'].setName('SyntheticOEM-'+asset,nameid,3,1,0x409)
                font.save(stock)
        target['path']=f'/system/fonts/SyntheticRoute{i:02d}.ttf'
        target['targetContract']['stockIdentity']={'logicalPath':target['path'],'faceIndex':0,'sha256':digest(stock),
            'buildKey':'synthetic-benchmark','provenance':{'schema':'stock-view-proof-v1','verified':True,'testFixture':True}}
        target['targetContract'].pop('stockGeometryProfile',None)
        artifact=compiler._physical_artifact(target,plan)
        artifact['requiredWeight']=[400,100,700][i%3] if kind in {'ui','cjk-vf','latin-vf'} else 400
        cases.append((kind,stock,{'target':target,'artifact':artifact,'deploymentKinds':['physical-slot'],'routeNodes':[]}))
    reports={};modes=['baseline','optimized'] if mode=='both' else [mode]
    # Known synthetic inputs only. Production verification is never disabled.
    with patch('stock_font_provenance.verify_stock_path',return_value={'schema':'stock-view-proof-v1','verified':True,'testFixture':True}):
        for current in modes:
            output=root/current;output.mkdir(exist_ok=True);cache={} if current=='optimized' else None
            started=time.monotonic();units=[]
            with patch.object(compiler,'_PROBE_ONLY_ENABLED',current=='optimized'):
                for index,(kind,stock,unit) in enumerate(cases):
                    begin=time.monotonic();result=compiler._compile_unit(unit,{unit['target']['path']:stock},output,False,cache)
                    entry={'index':index,'kind':kind,'seconds':round(time.monotonic()-begin,6),
                           'status':result['status'],'reason':result.get('reason'),'sha256':result.get('sha256'),
                           'bytes':result.get('bytes'),'renderReuse':result.get('report',{}).get('renderReuse',{}).get('hit'),
                           'donorReuse':result.get('report',{}).get('replaced',{}).get('preparedDonorReuse',{})}
                    units.append(entry);print(json.dumps({'mode':current,**entry}),flush=True)
            reports[current]={'seconds':round(time.monotonic()-started,6),
                'peakRssMiBProcessLifetime':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,'units':units}
            if any(u['status']!='ready' for u in units):raise AssertionError('benchmark requires every unit ready')
    if mode=='both':
        a=[u['sha256'] for u in reports['baseline']['units']];b=[u['sha256'] for u in reports['optimized']['units']]
        if a!=b:raise AssertionError('optimized output bytes differ from complete-instance reference')
    report={'synthetic':True,'androidValidated':False,'hanRequested':han,'actualHan':actual_han,'contours':contours,
            'sourceBytes':source.stat().st_size,'largeVariableBytes':big.stat().st_size,'unitCount':len(cases),
            'note':'RSS is process-lifetime high-water; use separate --mode runs for independent peaks.', 'runs':reports}
    (root/'benchmark.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='runs'}|{'times':{k:v['seconds'] for k,v in reports.items()}}))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--han',type=int,default=6000);p.add_argument('--contours',type=int,default=1)
    p.add_argument('--mode',choices=('baseline','optimized','both'),default='optimized')
    p.add_argument('--smoke',action='store_true');p.add_argument('--output-dir',type=Path)
    a=p.parse_args()
    if a.han<6000 or a.han>65000 or a.contours<1 or a.contours>48:p.error('use 6000..65000 Han and 1..48 contours')
    if a.output_dir:run(a.output_dir,a.han,a.contours,a.mode,a.smoke)
    else:
        with tempfile.TemporaryDirectory(prefix='luoshu-fixed-benchmark-') as d:run(Path(d),a.han,a.contours,a.mode,a.smoke)
