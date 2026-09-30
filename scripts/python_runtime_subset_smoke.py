#!/usr/bin/env python3
"""Host import/execute check with pruned stdlib families made unavailable.

Uses staged FontTools when PYTHONPATH points there; not an Android ABI claim.
"""
import sys
# Host Python 3.12 pathlib eagerly imports urllib.parse; Android's retained
# Python 3.14 pathlib does not. Load fixture stdlib before guarding FontTools,
# then discard any removed-family modules so font code cannot inherit them.
import hashlib
from pathlib import Path
import tempfile
class PrunedModules:
    removed = {'asyncio','concurrent','multiprocessing','email','http','urllib','html',
               'xmlrpc','wsgiref','unittest','sqlite3','ssl','imaplib','ftplib','smtplib',
               'mailbox','webbrowser','socketserver','ipaddress','doctest','trace',
               'modulefinder','compileall'}
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in self.removed:
            raise ImportError('module intentionally absent from Android payload: '+fullname)
sys.meta_path.insert(0,PrunedModules())
for name in list(sys.modules):
    if name.split('.')[0] in PrunedModules.removed:
        del sys.modules[name]
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'scripts')]
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.TupleVariation import TupleVariation
import universal_font_compiler_test as fixture
from stock_geometry_profile import capture_geometry_profile
with tempfile.TemporaryDirectory() as raw:
    source=Path(raw)/'stock.ttf'
    fixture.make_font(source,family='Pruned Runtime VF',variable=True)
    with TTFont(source) as font:
        name=font.getBestCmap()[ord('A')]
        count=len(font['glyf'][name].getCoordinates(font['glyf'])[0])
        font['gvar'].variations[name]=[TupleVariation({'wght':(0,1,1)},[(0,30)]*count+[(0,0)]*4)]
        font.save(source)
    before=source.read_bytes()
    result=capture_geometry_profile(source,0,dict(sha256=hashlib.sha256(before).hexdigest(),faceIndex=0))
    assert result['profile']['probes']['latinCap']['boundsHits']>0
    assert result['location']=={'wght':400.0}
    assert source.read_bytes()==before
print('python_runtime_subset_smoke: PASS (pruned imports blocked, actual variable subset/capture)')
