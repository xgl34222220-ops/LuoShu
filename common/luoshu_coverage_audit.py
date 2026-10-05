#!/usr/bin/env python3
"""Account for every system-topology path without inferring App rendering.

This is a read-only report builder. A successful file replacement is an action,
not evidence that its source contains all English letters/digits, nor that an
App uses that file. Coverage is measured only from explicit cmap counts. In
particular the role classifier's absent-metrics -> zero diagnostic defaults
are deliberately not used as measurements here.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

SCHEMA = "luoshu-system-font-coverage-audit-v1"
VERSION = 1
STATUSES = ("full-replaced", "partial-replaced", "kept-text",
            "protected-nontext", "unmeasured")
TEXT_ROLES = {"ui-sans", "cjk", "latin", "clock", "numeric", "broad-text",
              "serif", "monospace", "special-fallback"}
PROTECTED_ROLES = {"emoji", "symbol-icon"}


def _count(value: Any, maximum: int) -> int | None:
    # A presence boolean, total glyph count, or invalid count is not a cmap
    # measurement of the 52 ASCII letters / ten ASCII digits.
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 0 <= value <= maximum:
        return value
    return None


def _coverage(raw: Any, letter_key: str, digit_key: str) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    letters = _count(raw.get(letter_key), 52)
    digits = _count(raw.get(digit_key), 10)
    measurement = "measured" if letters is not None and digits is not None \
        else "partial" if letters is not None or digits is not None else "unknown"
    return {"measurement": measurement, "asciiLetters": letters, "asciiDigits": digits}


def _complete(coverage: dict[str, Any]) -> bool | None:
    letters, digits = coverage["asciiLetters"], coverage["asciiDigits"]
    if letters is not None and letters < 52 or digits is not None and digits < 10:
        return False
    if letters is None or digits is None:
        return None
    return letters == 52 and digits == 10


def _retained_present(before: dict[str, Any], replacement: dict[str, Any],
                      matched_stock_counts: bool) -> dict[str, int | None]:
    """Unchanged/missing original ASCII, with unknown distinct from zero.

    Partial merge counts measure the original cmap's matched characters. A
    whole replacement's source cmap count does not establish intersection
    with an incomplete stock cmap: stock 26 + source 51 is not proof all 26
    stock letters were copied. Complete-source or complete-stock counts do
    establish that intersection without needing full codepoint sets.
    """
    result: dict[str, int | None] = {}
    for field, maximum, label in (("asciiLetters", 52, "letters"), ("asciiDigits", 10, "digits")):
        original, changed = before[field], replacement[field]
        if original is None:
            result[label] = None
        elif original == 0:
            result[label] = 0
        elif changed is None:
            result[label] = None
        elif matched_stock_counts or changed in {0, maximum} or original == maximum:
            result[label] = max(original - changed, 0)
        else:
            result[label] = None
    return result


def build_audit(topology: dict[str, Any], roles: dict[str, Any],
                replaced: list[dict[str, Any]], kept: dict[str, str]) -> dict[str, Any]:
    """Return one disposition per topology key, using the supplied exact roles.

    Optional replacement ``sourceCoverage`` counts must describe the minimum
    coverage across *all selected output faces*. Older full replacements have
    no such evidence and remain unknown. Partial replacements require the
    merge's explicit ASCII codepoint counts; aggregate glyph counts cannot
    establish ASCII coverage. No fonts, APKs or process state are read here.
    """
    slots = topology.get("slots") if isinstance(topology.get("slots"), dict) else {}
    role_slots = roles.get("slots") if isinstance(roles.get("slots"), dict) else {}
    kept = kept if isinstance(kept, dict) else {}
    records = replaced if isinstance(replaced, list) else []
    actions: dict[str, dict[str, Any]] = {}
    issues: list[dict[str, Any]] = []
    outside: list[str] = []
    for index, item in enumerate(records):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            issues.append({"kind": "invalid-replacement-record", "index": index})
            continue
        path = item["path"]
        if path not in slots:
            outside.append(path)
            continue
        if path in actions:
            issues.append({"kind": "duplicate-replacement-path", "path": path})
        actions[path] = item

    paths: list[dict[str, Any]] = []
    for path in sorted(slots):
        raw_slot = slots[path]
        slot = raw_slot if isinstance(raw_slot, dict) else {}
        role_data = role_slots.get(path)
        role_data = role_data if isinstance(role_data, dict) else {}
        role = str(role_data.get("role") or "unknown-protected")
        metrics = slot.get("metrics") if isinstance(slot.get("metrics"), dict) else {}
        before = _coverage(metrics.get("coverage"), "latinCount", "digitCount")
        source = _coverage({}, "asciiLetters", "asciiDigits")
        replacement = _coverage({}, "asciiLettersReplaced", "asciiDigitsReplaced")
        action = actions.get(path)
        dynamic = path.startswith("/data/")
        protected = role in PROTECTED_ROLES or dynamic
        if action is not None:
            partial = action.get("mode") == "partial-stock"
            # The partial merge has the actual original cmap in hand. Prefer
            # its explicit count over absent/stale scanner measurements; a
            # missing field still keeps the topology's real measurement.
            for target_key, proof_key, maximum in (("asciiLetters", "asciiLettersBefore", 52),
                                                   ("asciiDigits", "asciiDigitsBefore", 10)):
                measured = _count(action.get(proof_key), maximum)
                if measured is not None:
                    before[target_key] = measured
            before = _coverage(before, "asciiLetters", "asciiDigits")
            status = "partial-replaced" if partial else "full-replaced"
            reason = "partial-stock-text-glyphs" if partial else "full-file-replacement"
            source = _coverage(action.get("sourceCoverage"), "asciiLetters", "asciiDigits")
            replacement = _coverage(action, "asciiLettersReplaced", "asciiDigitsReplaced")
            # For a whole-file replacement the source's measured cmap is the
            # output cmap. Never apply this shortcut to a partial replacement.
            if not partial and replacement["measurement"] == "unknown":
                replacement = dict(source)
            if path in kept:
                issues.append({"kind": "replacement-and-kept-conflict", "path": path})
            if protected:
                issues.append({"kind": "protected-path-replaced", "path": path})
        elif protected:
            status = "protected-nontext"
            reason = str(kept.get(path) or ("dynamic-font" if dynamic else "protected-role"))
        else:
            measured_text = (before["asciiLetters"] or 0) > 0 or (before["asciiDigits"] or 0) > 0
            status = "kept-text" if role in TEXT_ROLES or measured_text or path in kept else "unmeasured"
            reason = str(kept.get(path) or ("role-whitelist" if status == "kept-text"
                                          else "coverage-unmeasured"))
        if action is None:
            # This is a known action count (no glyphs changed), independent
            # of whether the original font's cmap was measured.
            replacement = _coverage({"asciiLettersReplaced": 0, "asciiDigitsReplaced": 0},
                                    "asciiLettersReplaced", "asciiDigitsReplaced")
        retained = _retained_present(before, replacement,
                                     action is None or action.get("mode") == "partial-stock")
        present_complete = None if any(value is None for value in retained.values()) \
            else all(value == 0 for value in retained.values())
        entry: dict[str, Any] = {
            "path": path, "role": role, "status": status, "reason": reason,
            "beforeCoverage": before, "sourceCoverage": source,
            "replacementCoverage": replacement,
            "asciiComplete": _complete(replacement) if action is not None else None,
            "originalAsciiComplete": _complete(before),
            "retainedPresentAscii": retained,
            "presentAsciiComplete": present_complete,
        }
        if action is not None:
            entry["replacementRole"] = str(action.get("role") or role)
            if action.get("mode") == "partial-stock":
                # Keep the merge's actual safety boundary visible, even when
                # shared glyphs leave some ASCII characters unchanged.
                entry["partialBoundary"] = {
                    key: action[key] for key in ("protectedSharedGlyphs", "protectedLayoutGlyphs", "protectedMetricGlyphs",
                                                "layoutCoverage", "advancePolicy") if key in action
                }
        if protected:
            entry["protectionReason"] = "dynamic-font" if dynamic else role
        if not isinstance(raw_slot, dict):
            entry["reason"] = "invalid-topology-slot"
            issues.append({"kind": "invalid-topology-slot", "path": path})
        paths.append(entry)

    status_counts = Counter(item["status"] for item in paths)
    before_counts = Counter(item["beforeCoverage"]["measurement"] for item in paths)
    source_counts = Counter(item["sourceCoverage"]["measurement"] for item in paths)
    complete_counts = Counter("unknown" if item["asciiComplete"] is None else
                              "complete" if item["asciiComplete"] else "incomplete" for item in paths
                              if item["status"] in {"full-replaced", "partial-replaced"})
    return {
        "schema": SCHEMA, "version": VERSION, "scope": "system-font-topology",
        "appRendering": "not-assessed",
        "asciiDefinition": {"letters": "A-Z,a-z", "letterCount": 52,
                            "digits": "0-9", "digitCount": 10},
        "topologyPathCount": len(slots), "auditedPathCount": len(paths),
        "statusCounts": {status: status_counts[status] for status in STATUSES},
        "beforeMeasurementCounts": {key: before_counts[key] for key in ("measured", "partial", "unknown")},
        "sourceMeasurementCounts": {key: source_counts[key] for key in ("measured", "partial", "unknown")},
        "replacedAsciiCounts": {key: complete_counts[key] for key in ("complete", "incomplete", "unknown")},
        "replacedPathCount": len(actions),
        "replacementRecordCount": len(records),
        "replacementPathsOutsideTopology": sorted(set(outside)),
        "keptPathsOutsideTopology": sorted(path for path in kept if path not in slots),
        "integrityIssues": issues, "paths": paths,
    }
