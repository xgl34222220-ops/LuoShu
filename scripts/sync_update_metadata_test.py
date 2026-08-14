#!/usr/bin/env python3
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_update_metadata", ROOT / "scripts" / "sync_update_metadata.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

meta = mod.build_metadata(
    repository="xgl34222220-ops/LuoShu",
    version="v2.4.1 Beta 1",
    version_code=20401,
    tag="v2.4.1-Beta-1",
    notes_file="RELEASE_NOTES_v2.4.1_Beta_1.md",
)
assert meta == {
    "version": "v2.4.1 Beta 1",
    "versionCode": 20401,
    "zipUrl": "https://github.com/xgl34222220-ops/LuoShu/releases/download/v2.4.1-Beta-1/LuoShu-v2.4.1-Beta-1.zip",
    "changelog": "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/v2.4.1-Beta-1/RELEASE_NOTES_v2.4.1_Beta_1.md",
}

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
