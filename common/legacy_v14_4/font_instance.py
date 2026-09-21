#!/usr/bin/env python3
"""Keep the legacy entry point, but use the single shared font instancer.

Resolve the symlink used by mix_router before locating common/. Legacy mixing
intentionally preserves source metrics; its final slot pass aligns them later.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


def main() -> int:
    try:
        canonical = Path(__file__).resolve().parents[1] / "font_instance.py"
        spec = importlib.util.spec_from_file_location("_luoshu_shared_font_instance", canonical)
        if spec is None or spec.loader is None:
            raise RuntimeError("共享字体实例化引擎不可用，请安装配套模块")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.main(preserve_metrics_default=True)
    except Exception as error:
        print(json.dumps({"status": "error", "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
