#!/usr/bin/env python3
import importlib.util
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("sync_update_metadata", ROOT / "scripts" / "sync_update_metadata.py")
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

module_prop = {}
for raw_line in (ROOT / "module.prop").read_text(encoding="utf-8").splitlines():
    if "=" not in raw_line:
        continue
    key, value = raw_line.split("=", 1)
    module_prop[key.strip()] = value.strip()

version = module_prop["version"]
version_code = int(module_prop["versionCode"])
tag = version
notes_file = f"RELEASE_NOTES_{version}.md"
assert (ROOT / notes_file).is_file(), notes_file

meta = mod.build_metadata(
    repository="xgl34222220-ops/LuoShu",
    version=version,
    version_code=version_code,
    tag=tag,
    notes_file=notes_file,
)
artifact = mod.artifact_version(version)
assert meta == {
    "version": version,
    "versionCode": version_code,
    "zipUrl": f"https://github.com/xgl34222220-ops/LuoShu/releases/download/{tag}/LuoShu-{artifact}.zip",
    "changelog": f"https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/{tag}/{notes_file}",
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
