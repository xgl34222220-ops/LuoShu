#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def role_for_weight(value: int) -> str:
    if value <= 149:
        return "thin"
    if value <= 249:
        return "extralight"
    if value <= 349:
        return "light"
    if value <= 449:
        return "regular"
    if value <= 549:
        return "medium"
    if value <= 649:
        return "semibold"
    if value <= 749:
        return "bold"
    if value <= 849:
        return "extrabold"
    return "black"


def parse_weights(raw: str) -> list[int]:
    values: set[int] = set()
    for item in (raw or "").split(","):
        item = item.strip()
        if item.isdigit():
            values.add(max(1, min(1000, int(item))))
    return sorted(values or {400})


def read_records(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    with path.open("r", encoding="utf-8", errors="replace") as stream:
        for raw in stream:
            line = raw.rstrip("\n")
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 11:
                continue
            file_path, family, weights, variable, fmt, size, mtime, valid, error, metadata, relative = parts[:11]
            try:
                size_value = int(size)
            except ValueError:
                size_value = 0
            records.append({
                "path": file_path,
                "relative": relative,
                "family": family.strip() or Path(file_path).stem,
                "weights": parse_weights(weights),
                "variable": variable == "true",
                "format": fmt or Path(file_path).suffix.lstrip(".").upper() or "UNKNOWN",
                "bytes": size_value,
                "date": mtime,
                "valid": valid == "true",
                "error": error,
                "metadata": metadata == "true",
            })
    return records


def format_size(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value // 1024} KB"
    if value < 1024 * 1024 * 1024:
        return f"{value / (1024 * 1024):.1f} MB"
    return f"{value / (1024 * 1024 * 1024):.1f} GB"


def build_index(records: list[dict[str, object]], current: str) -> dict[str, object]:
    groups: dict[str, list[dict[str, object]]] = {}
    for record in records:
        family = str(record["family"])
        if not family or family == "LuoShuAppMix":
            continue
        groups.setdefault(family, []).append(record)

    fonts: list[dict[str, object]] = []
    total_size = 0
    pending = False
    for family in sorted(groups, key=str.casefold):
        items = groups[family]
        total_size += sum(int(item["bytes"]) for item in items)
        pending = pending or any(not bool(item["metadata"]) for item in items)
        weights = sorted({weight for item in items for weight in item["weights"]})
        representative = min(items, key=lambda item: (
            min(abs(int(weight) - 400) for weight in item["weights"]),
            0 if bool(item["valid"]) else 1,
            -int(item["bytes"]),
        ))
        roles: list[str] = []
        variants: dict[str, str] = {}
        for weight in weights:
            role = role_for_weight(int(weight))
            if role not in roles:
                roles.append(role)
            candidate = min(items, key=lambda item: min(abs(int(source_weight) - int(weight)) for source_weight in item["weights"]))
            variants[role] = "./fonts/" + str(candidate["relative"])
        variable = any(bool(item["variable"]) for item in items)
        valid = any(bool(item["valid"]) for item in items)
        first_error = next((str(item["error"]) for item in items if item["error"]), "")
        fonts.append({
            "id": family,
            "name": family,
            "weights": roles,
            "variants": variants,
            "familyType": "variable" if variable else "static-family" if len(weights) > 1 or len(items) > 1 else "single",
            "file": "./fonts/" + str(representative["relative"]),
            "size": format_size(int(representative["bytes"])),
            "bytes": int(representative["bytes"]),
            "format": str(representative["format"]),
            "valid": valid,
            "warning": "" if all(bool(item["metadata"]) for item in items) else "字体已显示，内部信息正在后台补全",
            "error": "" if valid else first_error or "字体文件不可用",
            "variable": variable,
            "date": str(representative["date"]),
        })
    return {
        "status": "ok",
        "data": {
            "current": current or "default",
            "scanner": {"primary": "fast-index", "metadataPending": pending},
            "stats": {"count": len(fonts), "files": len(records), "totalSize": format_size(total_size)},
            "fonts": fonts,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--records", required=True)
    parser.add_argument("--current", default="default")
    args = parser.parse_args()
    print(json.dumps(build_index(read_records(Path(args.records)), args.current), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
