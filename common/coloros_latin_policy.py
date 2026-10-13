"""ColorOS / OxygenOS / realme UI (OPlus) Latin and digit slot policy.

Single source for the OPlus filenames that the ColorOS mappers learned after
ColorOS 15/16 (2026-10).  The shell mappers carry plain copies of the lists in
``LUOSHU_COLOROS_LATIN_POLICY`` blocks:

* ``common/legacy_v14_4/rom_adapters.sh`` (legacy safe-switch mapper, the
  active App chain) and
* ``common/coloros_global.sh`` (partition-aware v4 mapper),

and ``scripts/coloros_latin_coverage_test.py`` fails when a copy drifts.  The
ColorOS metrics post-pass (``coloros_metrics_batch.py``) imports this module.

Facts (public firmware dumps of ColorOS 15 CN / ColorOS 16 CN+ROW, see
docs/COLOROS_LATIN_COVERAGE_2026-10.md):

* ``/system_ext/etc/fonts_base.xml`` declares ``<family name="osans-solid-digits">``
  backed by ``OSans-Solid-Digits-VF.ttf`` (digits, currency signs and number
  punctuation only, variable ``wght`` 100-1000).  No LuoShu list or discovery
  prefix matched ``OSans-*``, so digits drawn through that family stayed stock.
* ``OSans-RC-Regular.ttf`` is a 60k-Han rare-character CJK store (no Latin) and
  ``OSans-Ext-Regular.otf`` a 7-code-point placeholder.  Both are default
  fallback families; replacing them would turn rare Han into tofu, so they are
  always kept stock (same rule as HyperOS ``MiSansL3``).
* ``SysFont-*.ttf`` in ``/system/fonts`` are symlinks into the OPlus flip-font
  directory ``/data/format_unclear/font`` (``OplusOSUI-*.ttf``), whose init
  links point back to ``/system/fonts`` and can dangle (``Roboto-Medium.ttf``
  does not exist on ColorOS 15/16) or loop (``SysFont-Hans-Regular.ttf``).
  A stock symlink is a real slot even when its chain does not resolve.

Optional group (``config/coloros_slot_groups.conf``, ``key=0|1`` lines):

* ``osans_digits``  ``OSans-*Digits*``  default on.  A digits/display face is
  replaced like other measured numeric faces; set ``osans_digits=0`` to keep the
  OPlus numerals (e.g. if a proportional user font makes tabular counters jump).

Monospace, clock, serif, emoji, symbol and script faces keep their existing
rules (they are never added here).
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# Bump when the lists below change which stock files a mapper targets; the v4
# target cache and the legacy safe-switch cache both include it.
POLICY_REVISION = 1

GROUP_DEFAULTS = {"osans_digits": True}

# Exact OPlus digit faces known from firmware; discovery adds future
# ``OSans-*Digits*`` renames (upright, single-face TTF/OTF only).
DIGIT_FILES = ("OSans-Solid-Digits-VF.ttf",)
DIGIT_DISCOVERY_GLOBS = ("OSans-*Digits*",)

# Always stock: rare-Han store and placeholder fallback.
KEEP_STOCK_FILES = ("OSans-RC-Regular.ttf", "OSans-Ext-Regular.otf")
KEEP_STOCK_PREFIXES = ("OSans-RC", "OSans-Ext")

_DIGIT_RE = re.compile(r"^OSans-[A-Za-z0-9_.-]*Digits[A-Za-z0-9_.-]*\.(?:ttf|otf)$")
_EXCLUDE_TOKENS = ("italic", "oblique", "mono", "clock", "serif", "emoji", "symbol", "icon")


def _module_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def groups_config_path() -> Path:
    raw = os.environ.get("LUOSHU_COLOROS_SLOT_GROUPS_CONF", "").strip()
    if raw:
        return Path(raw)
    module = (os.environ.get("LUOSHU_REAL_MODDIR") or os.environ.get("MODDIR")
              or os.environ.get("MODULE_DIR") or "").strip()
    return (Path(module) if module else _module_dir()) / "config" / "coloros_slot_groups.conf"


def parse_groups(text: str) -> frozenset[str]:
    """``key=0|1`` lines; anything else is ignored. Same rule as the shell reader."""
    state = dict(GROUP_DEFAULTS)
    for line in text.split("\n"):
        key, sep, value = line.partition("=")
        value = value[:-1] if value.endswith("\r") else value
        if sep and key in state and value in ("0", "1"):
            state[key] = value == "1"
    return frozenset(name for name, on in state.items() if on)


def enabled_groups(path: Path | None = None) -> frozenset[str]:
    try:
        text = (path or groups_config_path()).read_text(encoding="utf-8", errors="replace")
    except OSError:
        text = ""
    return parse_groups(text)


def classify(name: str) -> str:
    """``digits`` | ``keep`` | ``other`` for a stock basename."""
    base = Path(name).name
    if base in KEEP_STOCK_FILES or base.startswith(KEEP_STOCK_PREFIXES):
        return "keep"
    lowered = base.lower()
    if any(token in lowered for token in _EXCLUDE_TOKENS):
        return "other"
    if base in DIGIT_FILES or _DIGIT_RE.match(base):
        return "digits"
    return "other"


def keeps_stock(name: str, groups: frozenset[str] | None = None) -> bool:
    """True when the ColorOS policy must leave this stock file untouched."""
    kind = classify(name)
    if kind == "keep":
        return True
    if kind == "digits":
        return "osans_digits" not in (enabled_groups() if groups is None else groups)
    return False


def mapped_digit_name(name: str, groups: frozenset[str] | None = None) -> bool:
    """A digit face this policy maps (eligible for the stock metrics contract)."""
    return classify(name) == "digits" and not keeps_stock(name, groups)


def main(argv: list[str]) -> int:
    if argv[1:] == ["--groups"]:
        print(" ".join(sorted(enabled_groups())))
        return 0
    if len(argv) == 3 and argv[1] == "--classify":
        print(classify(argv[2]))
        return 0
    print("usage: coloros_latin_policy.py --groups | --classify <name>", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
