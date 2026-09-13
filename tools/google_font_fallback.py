#!/usr/bin/env python3
"""Source-tree CLI wrapper; the bundled implementation is authoritative."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'common'))
from google_font_fallback import main
if __name__ == '__main__':
    raise SystemExit(main())
