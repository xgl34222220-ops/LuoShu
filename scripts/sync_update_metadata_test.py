#!/usr/bin/env python3
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_update_metadata", ROOT / "scripts" / "sync_update_metadata.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

meta = mod.build_metadata(
    repository="xgl34222220-ops/LuoShu",
    version="v4.0.0",
    version_code=40000,
    tag="v4.0.0",
    notes_file="RELEASE_NOTES_v4.0.0.md",
)
assert meta == {
    "version": "v4.0.0",
    "versionCode": 40000,
    "zipUrl": "https://github.com/xgl34222220-ops/LuoShu/releases/download/v4.0.0/LuoShu-v4.0.0.zip",
    "changelog": "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/v4.0.0/RELEASE_NOTES_v4.0.0.md",
}

for metadata_file in ("update.json", "update-prerelease.json"):
    actual = json.loads((ROOT / metadata_file).read_text(encoding="utf-8"))
    assert actual == meta, (metadata_file, actual)

for kwargs in (
    dict(repository="bad", version="v1", version_code=1, tag="v1", notes_file="n"),
    dict(repository="a/b", version="v1", version_code=0, tag="v1", notes_file="n"),
):
    try:
        mod.build_metadata(**kwargs)
    except ValueError:
        pass
    else:
        raise AssertionError(f"expected ValueError: {kwargs}")

print("update metadata tests passed")
