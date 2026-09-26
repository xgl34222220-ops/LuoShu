#!/usr/bin/env python3
"""Plan composite weights from retained device faces, without opening font data."""
from __future__ import annotations

import json
from pathlib import Path
import sys


def required_weights(inventory: dict) -> list[int]:
    slots = inventory.get('slots')
    if not isinstance(slots, dict):
        raise ValueError('本机字体清单缺少槽位记录')
    weights = set()
    for slot in slots.values():
        if slot.get('preservedReason'):
            continue
        for face in slot.get('faces') or [slot]:
            if face.get('preservedReason'):
                continue
            metrics = face.get('metrics') or {}
            traits = metrics.get('fontTraits') or {}
            if traits.get('color') or traits.get('symbol'):
                continue
            weight = int(face.get('weight', metrics.get('weightClass', 400)))
            if not 1 <= weight <= 1000:
                raise ValueError('本机字体清单包含无效字重')
            weights.add(weight)
    if not weights:
        raise ValueError('本机字体清单没有可生成的文字字重')
    return sorted(weights)


if __name__ == '__main__':
    try:
        print(' '.join(map(str, required_weights(json.loads(Path(sys.argv[1]).read_text())))))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f'读取本机字重清单失败：{exc}', file=sys.stderr)
        raise SystemExit(1)
