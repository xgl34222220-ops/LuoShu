#!/usr/bin/env python3
"""Exercise the actual scanner fixture and inspect persisted slot archives."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
import font_inventory_scan_test as fixture
import universal_font_plan as planner

original_run = fixture.run
checked = 0

def checking_run(command, env=None):
    global checked
    result = original_run(command, env)
    if result.returncode == 0 and '--output' in command:
        output = Path(command[command.index('--output') + 1])
        if output.is_file():
            inventory = json.loads(output.read_text())
            for logical, slot in inventory.get('slots', {}).items():
                identity = slot['stockIdentity']
                archive = slot['stockGeometryProfile']
                assert identity['logicalPath'] == logical
                assert archive['stockSha256'] == identity['sha256']
                assert archive['faceIndex'] == identity['faceIndex']
                assert archive['profile']['probes']
                assert archive['profile']['metrics']['unitsPerEm'] > 0
                assert not archive['profile']['path']
                target = planner._plan_slot(logical, slot, {'role':'unknown-protected'}, [])
                assert target['targetContract']['stockGeometryProfile'] == archive
                assert target['targetContract']['stockIdentity'] == identity
                checked += 1
    return result

if __name__ == '__main__':
    fixture.run = checking_run
    assert fixture.main() == 0
    assert checked > 0
    print(f'stock_geometry_scan_test: PASS ({checked} persisted slot checks)')
