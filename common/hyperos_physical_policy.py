"""Single source of truth for HyperOS physical font file targets.

Every HyperOS filename list in the module is derived from this file:

* the stock scanner (font_inventory_scan.py) and the staging metrics batch
  (hyperos_metrics_batch.py) import it directly;
* the shell mappers (legacy_v14_4/hyperos_clock_compat.sh,
  legacy_v14_4/hyperos_full_coverage.sh and hyperos_global.sh) carry a block
  GENERATED from it by ``python3 common/hyperos_physical_policy.py --write``.
  CI runs ``--check`` so a hand edit of a shell copy, or a policy change without
  regeneration, fails instead of silently forking the XML and physical routes;
* the HyperOS seed-XML rewrite (hyperos_source_xml.py) consults
  ``xml_file_allowed`` so XML never replaces a file the physical route keeps.

Optional slot groups (config/hyperos_slot_groups.conf, ``key=0|1`` lines):

* ``miui_ex``           MiuiEx-*, Miui-*                         default on
* ``misans_ext``        MiSansRounded*, MiSansC* (not clock), MiLanVF*  default on
* ``lockscreen_styles`` lock screen / AOD / widget display faces  default off

Always kept stock: italic/serif/emoji/symbol/icon/script faces, collections,
MiSansL3 (GB18030 rare-character store; replacing it turns rare Han into tofu)
and every clock/tabular ``*Mono*`` face (MitypeMonoVF, MitypeClockMono*,
MiClockMono*, InterMono*, BebasNeue-Mono, any ``*Clock*Mono*``: digit slots must
never receive a proportional user font).

Code monospace faces behind the system ``monospace`` family (DroidSansMono.ttf,
RobotoMono*, NotoSansMono*) are replaced like other UI text, as before v4.3:
keeping them stock left terminal / flash-log screens (``FontFamily.Monospace``)
in the ROM font.
"""
from __future__ import annotations

import hashlib
import os
import re
import sys
from pathlib import Path


PARTITIONS = frozenset({
    "system", "system_ext", "product", "mi_ext", "vendor", "odm", "oem",
    "my_product", "hw_product", "cust",
})

DYNAMIC_OVERLAY_PATH = "/system/fonts/MiSansVF_Overlay.ttf"
DYNAMIC_OVERLAY_TARGET = "/data/system/fonts/theme_webview/Roboto-Regular.ttf"

# Bump font_inventory_scan.HYPEROS_COVERAGE_REVISION whenever this policy changes
# which stock files are captured, so installed inventories are rescanned.
POLICY_REVISION = 3


def preserved_dynamic_alias(data: dict, logical: str) -> bool:
    """Only the ROM-proven, framework-managed HyperOS WebView alias is exempt."""
    if logical != DYNAMIC_OVERLAY_PATH:
        return False
    alias = (data.get("preservedDynamicAliases") or {}).get(logical, {})
    if (alias.get("source") == "hyperos-framework-symlink"
            and alias.get("target") == DYNAMIC_OVERLAY_TARGET):
        return True
    # Test6 recorded this exact ROM symlink but incorrectly assumed its init
    # seed remained Roboto after the framework had selected a locale font.
    # This migration allows reapply before its deferred inventory refresh.
    slot = (data.get("slots") or {}).get(logical, {})
    return (slot.get("source") == "hyperos-rom-reference"
            and slot.get("metricsReferencePath") == "/system/fonts/Roboto-Regular.ttf")


_EXCLUDED = (
    "italic", "oblique", "emoji", "symbol", "serif", "arabic",
    "hebrew", "thai", "devanagari", "bengali", "tamil", "telugu", "malayalam",
    "gujarati", "gurmukhi", "kannada", "khmer", "lao", "tibetan", "myanmar",
    "vietnam", "japanese", "korean", "hangul", "hiragana", "katakana", "odia", "oriya",
    "cjkjp", "cjkkr",
)
_ICON_FALSE_POSITIVES = ("semicondensed", "gothicone")
_LANG_PREFIXES = ("MiSansJP", "MiSansJp", "MiSansKR", "MiSansKr")
_LANG_TOKENS = ("CJKJP", "CJKKR")
# GB18030-2022 level-3 rare characters (60k+ Han). A user font does not carry
# them, so this file stays stock and keeps serving as the rare-character store.
_RARE_HAN_PREFIXES = ("MiSansL3",)
# Any monospace/tabular face. Lower-case substring match.
MONO_TOKEN = "mono"
# Code monospace faces of the system ``monospace`` family. They are replaced
# (core) unless the name also carries CLOCK_TOKEN; every other Mono face stays
# stock. NotoSansMono uses exact-family matching so NotoSansMonoCJK*/Script*
# fallbacks are never treated as Latin UI.
CLOCK_TOKEN = "clock"
_CODE_MONO_NAMES = ("DroidSansMono.ttf",)
_CODE_MONO_PREFIXES = ("RobotoMono",)
_CODE_MONO_FAMILIES = ("NotoSansMono", "NotoSansMonoVF")

# Clock faces keep their own (core) handling even though "MiSansC" is the
# misans_ext prefix; checked before the group prefixes.
_CLOCK_BEFORE_GROUPS = ("MiSansClock",)

GROUPS = ("miui_ex", "misans_ext", "lockscreen_styles")
GROUP_DEFAULTS = {"miui_ex": True, "misans_ext": True, "lockscreen_styles": False}
GROUP_PREFIXES = {
    "miui_ex": ("MiuiEx", "Miui-"),
    "misans_ext": ("MiSansRounded", "MiSansC", "MiLanVF"),
    # HyperOS 3 lock screen / AOD / widget clock styles. Names come from a
    # third-party HyperOS 3 extraction (gizdev); confirm per device. InterMono
    # and BebasNeue-Mono are listed for completeness but the mono guard above
    # keeps them stock.
    "lockscreen_styles": (
        "Interscaled", "InterMono", "C800", "Qinghe", "ChamberiDisplay",
        "DelaGothicOne", "BebasNeue", "NeumaticCompressed", "GulfsDisplay",
    ),
}
ALL_GROUPS = frozenset(GROUPS)

_PREFIXES = (
    "MiSans", "XiaomiSans", "MiLanPro", "Mitype", "MiClock", "AndroidClock",
    "Roboto", "GoogleSans", "SourceSansPro",
)
_NOTO_UI_PREFIXES = (
    "NotoSans-", "NotoSansUI-", "NotoSansSC", "NotoSansTC", "NotoSansHK",
    "NotoSansHans", "NotoSansHant", "NotoSansCJKSC", "NotoSansCJKTC", "NotoSansCJKHK",
    "NotoSansCJKsc", "NotoSansCJKtc", "NotoSansCJKhk",
)
# These are Latin UI families, not language fallback prefixes. v4.3.0's
# narrowed NotoSans whitelist accidentally removed them from scanning, staging
# and boot repair. Match exact family names or a hyphenated style suffix, never
# restore the broad NotoSans* matcher that copied CJK into unrelated scripts.
_NOTO_LATIN_UI_FAMILIES = (
    "NotoSansMono", "NotoSansDisplay", "NotoSansCondensed",
    "NotoSansSemiCondensed", "NotoSansExtraCondensed",
    "NotoSansVF", "NotoSansVariable", "NotoSansUIVF",
    "NotoSansMonoVF", "NotoSansDisplayVF", "NotoSansCondensedVF",
)
_UI_NAMES = (
    "NotoSans.ttf", "NotoSans.otf", "NotoSansUI.ttf", "NotoSansUI.otf",
    "DroidSans.ttf", "DroidSans-Regular.ttf", "DroidSans-Bold.ttf", "Clockopia.ttf",
    "DroidSansMono.ttf", "DroidSansFallback.ttf",
)
_NUMERIC = tuple(f"{weight}.ttf" for weight in (100, 200, 300, 350, 400, 500, 600, 700, 800, 900))

# Names the boot repair checks even when a directory listing is unavailable.
# Filtered through the policy when the shell block is generated.
STATIC_NAMES = (
    "MiSansVF.ttf", "MiSansVF_Overlay.ttf", "MiSansLatinVF.ttf", "MiSansTCVF.ttf",
    *_NUMERIC,
    "Roboto-Thin.ttf", "Roboto-ExtraLight.ttf", "Roboto-Light.ttf", "Roboto-Regular.ttf",
    "Roboto-Medium.ttf", "Roboto-SemiBold.ttf", "Roboto-Bold.ttf", "Roboto-ExtraBold.ttf",
    "Roboto-Black.ttf", "RobotoFlex-Regular.ttf", "RobotoStatic-Regular.ttf",
    "GoogleSans-Regular.ttf", "GoogleSans-Medium.ttf", "GoogleSans-SemiBold.ttf",
    "GoogleSans-Bold.ttf", "GoogleSans-Black.ttf", "GoogleSansText-Regular.ttf",
    "GoogleSansText-Medium.ttf", "GoogleSansText-SemiBold.ttf", "GoogleSansText-Bold.ttf",
    "GoogleSansText-Black.ttf", "GoogleSansText-VF.ttf", "GoogleSansTextVF.ttf",
    "GoogleSans-VF.ttf", "GoogleSansFlex-Regular.ttf",
    "NotoSans-Regular.ttf", "NotoSans-Medium.ttf", "NotoSans-SemiBold.ttf",
    "NotoSans-Bold.ttf", "NotoSans-Black.ttf", "NotoSansUI-Regular.ttf",
    "NotoSansUI-Medium.ttf", "NotoSansUI-Bold.ttf", "SourceSansPro-Regular.ttf",
    "SourceSansPro-Medium.ttf", "SourceSansPro-SemiBold.ttf", "SourceSansPro-Bold.ttf",
    "DroidSans.ttf", "MitypeVF.ttf", "MitypeClock.ttf", "MitypeClock.otf",
    "MiClock.ttf", "MiClock.otf", "MiClockThin.ttf", "MiClockThin.otf",
    "MiSansClock.ttf", "MiSansClockVF.ttf", "AndroidClock.ttf",
    "AndroidClock_Highlight.ttf", "AndroidClock_Solid.ttf", "Clockopia.ttf",
    "MiuiEx-Regular.ttf", "MiuiEx-Light.ttf", "MiuiEx-Bold.ttf",
    "Miui-Regular.ttf", "Miui-Bold.ttf",
)
# Files earlier builds aliased that this policy now keeps stock. Mappers delete
# stale staged/overlay copies of these names. Code monospace names
# (DroidSansMono/RobotoMono/NotoSansMono) are replaced again and must not be here.
RETIRED_NAMES = (
    "MiSansL3.otf", "MitypeMonoVF.ttf", "MitypeClockMono.ttf", "MitypeClockMono.otf",
    "MiClockMono.ttf", "MiClockMono.otf",
)

# Every family prefix any HyperOS mapper writes. A staged alias with one of these
# prefixes that the policy rejects is removed so the ROM file shows through.
MAPPER_FAMILY_PREFIXES = (
    "MiSans", "XiaomiSans", "MiLanPro", "MiLanVF", "Mitype", "MiClock",
    "AndroidClock", "Roboto", "GoogleSans", "SourceSansPro",
    "NotoSans", "DroidSans", "Miui",
) + tuple(p for g in GROUPS for p in GROUP_PREFIXES[g] if not p.startswith(("Mi",)))


# ------------------------------------------------------------------ groups
def _module_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def groups_config_path() -> Path:
    raw = os.environ.get("LUOSHU_HYPEROS_SLOT_GROUPS_CONF", "").strip()
    if raw:
        return Path(raw)
    module = (os.environ.get("LUOSHU_REAL_MODDIR") or os.environ.get("MODDIR")
              or os.environ.get("MODULE_DIR") or "").strip()
    return (Path(module) if module else _module_dir()) / "config" / "hyperos_slot_groups.conf"


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


# ------------------------------------------------------------------ policy
def is_code_mono(name: str) -> bool:
    """System ``monospace`` text faces (terminals, logs), not clock/tabular digits."""
    if CLOCK_TOKEN in name.lower():
        return False
    stem = Path(name).stem
    return (name in _CODE_MONO_NAMES or name.startswith(_CODE_MONO_PREFIXES)
            or any(stem == family or stem.startswith(family + "-")
                   for family in _CODE_MONO_FAMILIES))


def classify(name: str) -> str:
    """Return why a filename is (not) a target, independent of group settings.

    ``invalid`` | ``excluded`` | ``rare-han`` | ``mono`` | ``core`` | a group id |
    ``unlisted``.
    """
    if not name or Path(name).name != name or not name.endswith((".ttf", ".otf")):
        return "invalid"
    lower = name.lower()
    # "SemiCondensed" / "DelaGothicOne" contain the substring "icon" across a
    # word boundary. Ignore those tokens only; a real Icon/Icons token still fails.
    icon_probe = lower
    for token in _ICON_FALSE_POSITIVES:
        icon_probe = icon_probe.replace(token, "")
    if "icon" in icon_probe:
        return "excluded"
    if any(token in lower for token in _EXCLUDED):
        return "excluded"
    if name.startswith(_LANG_PREFIXES) or any(token in name for token in _LANG_TOKENS):
        return "excluded"
    if name.startswith(_RARE_HAN_PREFIXES):
        return "rare-han"
    if MONO_TOKEN in lower:
        return "core" if is_code_mono(name) else "mono"
    if not name.startswith(_CLOCK_BEFORE_GROUPS):
        for group in GROUPS:
            if name.startswith(GROUP_PREFIXES[group]):
                return group
    # NotoSans is also the prefix of hundreds of unrelated script fallbacks.
    # A blacklist cannot enumerate them reliably; replacing each with the full
    # selected CJK donor both removes language coverage and multiplies storage.
    stem = Path(name).stem
    if (name.startswith(_PREFIXES + _NOTO_UI_PREFIXES)
            or name in _UI_NAMES or name in _NUMERIC
            or any(stem == family or stem.startswith(family + "-")
                   for family in _NOTO_LATIN_UI_FAMILIES)):
        return "core"
    return "unlisted"


def safe_physical_font_name(name: str, groups: frozenset[str] | set[str] | None = None) -> bool:
    """Single-face, upright physical filename policy shared by every mapper.

    ``groups`` defaults to config/hyperos_slot_groups.conf (defaults when absent).
    The stock scanner passes ``ALL_GROUPS`` so turning a group on later does not
    need a rescan; mappers use the configured set.
    """
    kind = classify(name)
    if kind == "core":
        return True
    if kind in GROUP_DEFAULTS:
        active = enabled_groups() if groups is None else groups
        return kind in active
    return False


def xml_file_allowed(name: str, generated: str = "", groups: frozenset[str] | None = None,
                     monospace_build: bool = False) -> bool:
    """May an XML ``<font>`` node naming stock ``name`` point at ``generated``?

    Clock/tabular Mono stock files may only receive a monospace-aware build: a ``LuoShuMono*``
    font, or a per-slot build whose role is ``mono``/``clock`` (stock-exact
    advances, ``monospace_build=True``). Rare-Han, excluded and disabled-group
    files never change. Names the physical policy does not list (e.g.
    ``Roboto-Regular.ttf`` shells, OEM-only names) are left to the per-slot
    template, which already decided they are UI slots.
    """
    kind = classify(name)
    if kind == "mono":
        return monospace_build or generated.startswith("LuoShuMono")
    if kind in ("rare-han", "excluded"):
        return False
    if kind in GROUP_DEFAULTS:
        active = enabled_groups() if groups is None else groups
        return kind in active
    return True


# ------------------------------------------------------- shell generation
GENERATED_BEGIN = "# >>> BEGIN GENERATED by common/hyperos_physical_policy.py --write (do not edit)"
GENERATED_END = "# <<< END GENERATED hyperos_physical_policy"
SHELL_TARGETS = (
    "common/legacy_v14_4/hyperos_clock_compat.sh",
    "common/legacy_v14_4/hyperos_full_coverage.sh",
    "common/hyperos_global.sh",
)


def _case_list(patterns: list[str]) -> str:
    return "|\\\n        ".join(patterns)


def render_shell_block() -> str:
    excluded = _case_list([f"*{t}*" for t in _EXCLUDED])
    lang = _case_list([f"{p}*" for p in _LANG_PREFIXES] + [f"*{t}*" for t in _LANG_TOKENS])
    rare = _case_list([f"{p}*" for p in _RARE_HAN_PREFIXES])
    clock_first = _case_list([f"{p}*" for p in _CLOCK_BEFORE_GROUPS])
    group_cases = []
    for group in GROUPS:
        group_cases.append(
            "        " + _case_list([f"{p}*" for p in GROUP_PREFIXES[group]])
            + f")\n            _lhpp_group_enabled {group}\n            return $?\n            ;;")
    core = _case_list([f"{p}*" for p in _PREFIXES + _NOTO_UI_PREFIXES] + list(_UI_NAMES) + list(_NUMERIC))
    families = " ".join(_NOTO_LATIN_UI_FAMILIES)
    code_mono = _case_list(list(_CODE_MONO_NAMES) + [f"{p}*" for p in _CODE_MONO_PREFIXES])
    code_families = " ".join(_CODE_MONO_FAMILIES)
    icon_fp = " ".join(_ICON_FALSE_POSITIVES)
    group_any = _case_list([f"{p}*" for g in GROUPS for p in GROUP_PREFIXES[g]])
    defaults = "; ".join(f"_LHPP_G_{g}={1 if GROUP_DEFAULTS[g] else 0}" for g in GROUPS)
    keys = "\n".join(f"                {g}) _LHPP_G_{g}=$_lhpp_v ;;" for g in GROUPS)
    statics = "\n".join(n for n in STATIC_NAMES
                         if classify(n) == "core" or classify(n) in GROUP_DEFAULTS)
    retired = " ".join(RETIRED_NAMES)
    groups_list = " ".join(GROUPS)
    body = f"""{GENERATED_BEGIN}
# policy revision {POLICY_REVISION}; source sha256 {policy_digest()}
_lhpp_groups_conf() {{
    if [ -n "${{LUOSHU_HYPEROS_SLOT_GROUPS_CONF:-}}" ]; then
        printf '%s\\n' "$LUOSHU_HYPEROS_SLOT_GROUPS_CONF"
    else
        printf '%s/config/hyperos_slot_groups.conf\\n' \\
            "${{LUOSHU_REAL_MODDIR:-${{MODDIR:-${{MODULE_DIR:-/data/adb/modules/LuoShu}}}}}}"
    fi
}}

_lhpp_load_groups() {{
    [ "${{_LHPP_LOADED:-}}" = 1 ] && return 0
    {defaults}
    _lhpp_conf=$(_lhpp_groups_conf)
    _lhpp_cr=$(printf '\\r')
    if [ -f "$_lhpp_conf" ]; then
        while IFS='=' read -r _lhpp_k _lhpp_v || [ -n "$_lhpp_k" ]; do
            case "$_lhpp_v" in *"$_lhpp_cr") _lhpp_v=${{_lhpp_v%"$_lhpp_cr"}} ;; esac
            case "$_lhpp_v" in 0|1) ;; *) continue ;; esac
            case "$_lhpp_k" in
{keys}
            esac
        done < "$_lhpp_conf"
    fi
    _LHPP_LOADED=1
}}

# Call after editing the groups file in the same shell.
_lhpp_reload_groups() {{
    _LHPP_LOADED=
    _lhpp_load_groups
}}

_lhpp_group_names() {{
    printf '%s\\n' '{groups_list}'
}}

_lhpp_group_enabled() {{
    _lhpp_load_groups
    eval "_lhpp_ge=\\${{_LHPP_G_$1:-0}}"
    [ "$_lhpp_ge" = 1 ]
}}

# Same decision as hyperos_physical_policy.safe_physical_font_name(name).
_lhpp_safe_name() {{
    _lhpp_name="$1"
    case "$_lhpp_name" in */*|'') return 1 ;; esac
    case "$_lhpp_name" in *.ttf|*.otf) ;; *) return 1 ;; esac
    _lhpp_lower=$(printf '%s' "$_lhpp_name" | tr '[:upper:]' '[:lower:]')
    # SemiCondensed / DelaGothicOne are not Icon fonts; strip only those tokens.
    _lhpp_icon=$_lhpp_lower
    for _lhpp_fp in {icon_fp}; do
        while :; do
            case "$_lhpp_icon" in
                *"$_lhpp_fp"*) _lhpp_icon=${{_lhpp_icon%%"$_lhpp_fp"*}}${{_lhpp_icon#*"$_lhpp_fp"}} ;;
                *) break ;;
            esac
        done
    done
    case "$_lhpp_icon" in *icon*) return 1 ;; esac
    case "$_lhpp_lower" in
        {excluded}) return 1 ;;
    esac
    case "$_lhpp_name" in
        {lang}) return 1 ;;
        {rare}) return 1 ;;
    esac
    case "$_lhpp_lower" in
        *{CLOCK_TOKEN}*) ;;
        *{MONO_TOKEN}*)
            # Code monospace (system monospace family) is replaced; see is_code_mono.
            case "$_lhpp_name" in
                {code_mono}) return 0 ;;
            esac
            _lhpp_stem=${{_lhpp_name%.*}}
            for _lhpp_family in {code_families}; do
                case "$_lhpp_stem" in
                    "$_lhpp_family"|"$_lhpp_family"-*) return 0 ;;
                esac
            done
            return 1
            ;;
    esac
    case "$_lhpp_lower" in *{MONO_TOKEN}*) return 1 ;; esac
    case "$_lhpp_name" in
        {clock_first}) ;;
        *)
            case "$_lhpp_name" in
{chr(10).join(group_cases)}
            esac
            ;;
    esac
    case "$_lhpp_name" in
        {core}) return 0 ;;
    esac
    _lhpp_stem=${{_lhpp_name%.*}}
    for _lhpp_family in {families}; do
        case "$_lhpp_stem" in
            "$_lhpp_family"|"$_lhpp_family"-*) return 0 ;;
        esac
    done
    return 1
}}

# True for a filename in any optional group (enabled or not).
_lhpp_group_member() {{
    case "$1" in
        {clock_first}) return 1 ;;
        {group_any}) return 0 ;;
    esac
    return 1
}}

# stdin: names (space or newline separated); stdout: accepted names, de-duplicated.
_lhpp_filter_names() {{
    tr ' ' '\\n' | while IFS= read -r _lhpp_fn; do
        [ -n "$_lhpp_fn" ] || continue
        _lhpp_safe_name "$_lhpp_fn" && printf '%s\\n' "$_lhpp_fn"
    done | awk 'NF && !seen[$0]++'
}}

# Group members are filtered at runtime so a disabled group adds nothing.
_lhpp_static_names() {{
    _lhpp_filter_names <<'EOF_LHPP_STATIC'
{statics}
EOF_LHPP_STATIC
}}

# Names earlier builds aliased that are now kept stock (stale-alias cleanup).
_lhpp_retired_names() {{
    printf '%s\\n' '{retired}'
}}
{GENERATED_END}"""
    return body


def policy_digest() -> str:
    """Digest of the policy data only (not of this generator's own output)."""
    data = repr((_EXCLUDED, _ICON_FALSE_POSITIVES, _LANG_PREFIXES, _LANG_TOKENS, _RARE_HAN_PREFIXES, MONO_TOKEN,
                 CLOCK_TOKEN, _CODE_MONO_NAMES, _CODE_MONO_PREFIXES, _CODE_MONO_FAMILIES,
                 _CLOCK_BEFORE_GROUPS, GROUPS, sorted(GROUP_DEFAULTS.items()),
                 sorted(GROUP_PREFIXES.items()), _PREFIXES, _NOTO_UI_PREFIXES,
                 _NOTO_LATIN_UI_FAMILIES, _UI_NAMES, _NUMERIC, STATIC_NAMES, RETIRED_NAMES,
                 POLICY_REVISION))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()[:16]


_BLOCK_RE = re.compile(re.escape(GENERATED_BEGIN) + r".*?" + re.escape(GENERATED_END), re.S)


def sync_shell(root: Path, write: bool) -> list[str]:
    """Return the targets whose generated block is missing or stale."""
    block = render_shell_block()
    stale = []
    for relative in SHELL_TARGETS:
        path = root / relative
        text = path.read_text(encoding="utf-8")
        found = _BLOCK_RE.findall(text)
        if len(found) != 1:
            stale.append(f"{relative}: expected exactly one generated block, found {len(found)}")
            continue
        if found[0] != block:
            stale.append(relative)
            if write:
                path.write_text(_BLOCK_RE.sub(lambda _m: block, text), encoding="utf-8")
    return stale


def main(argv: list[str]) -> int:
    root = _module_dir()
    if argv[1:2] == ["--write"]:
        changed = sync_shell(root, True)
        bad = [item for item in changed if ":" in item]
        for item in changed:
            print(("ERROR " if ":" in item else "regenerated ") + item)
        return 1 if bad else 0
    if argv[1:2] == ["--check"]:
        stale = sync_shell(root, False)
        for item in stale:
            print(f"stale generated HyperOS policy block: {item}", file=sys.stderr)
        if stale:
            print("run: python3 common/hyperos_physical_policy.py --write", file=sys.stderr)
        return 1 if stale else 0
    if argv[1:2] == ["--print"]:
        print(render_shell_block())
        return 0
    if argv[1:2] == ["--classify"]:
        for name in argv[2:]:
            print(f"{name}\t{classify(name)}\t{int(safe_physical_font_name(name))}")
        return 0
    print("usage: hyperos_physical_policy.py --write|--check|--print|--classify NAME...", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
