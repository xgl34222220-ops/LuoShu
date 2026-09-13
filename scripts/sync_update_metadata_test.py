#!/usr/bin/env python3
import importlib.util
import json
import pathlib
import tempfile

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

# Published channels may lag module.prop until signed assets are available.
for metadata_file in ("update.json", "update-prerelease.json"):
    actual = json.loads((ROOT / metadata_file).read_text(encoding="utf-8"))
    version = actual['version']
    assert isinstance(version, str) and version.startswith('v')
    assert mod.artifact_version(version) == version
    assert isinstance(actual['versionCode'], int) and actual['versionCode'] > 0
    release_tag = actual['zipUrl'].split('/releases/download/', 1)[1].split('/', 1)[0]
    assert release_tag in (version, 'refactor-' + version), (metadata_file, release_tag)
    notes_file = f"RELEASE_NOTES_{release_tag}.md"
    assert (ROOT / notes_file).is_file(), (metadata_file, notes_file)
    expected = mod.build_metadata(
        repository="xgl34222220-ops/LuoShu", version=version,
        version_code=actual['versionCode'], tag=release_tag, notes_file=notes_file,
    )
    assert actual == expected, (metadata_file, actual)

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

with tempfile.TemporaryDirectory() as directory:
    preview = pathlib.Path(directory) / 'preview.json'
    assert mod.advance_fallback_channel(meta, preview)
    assert json.loads(preview.read_text()) == meta
    newer = {**meta, 'versionCode': 40300, 'version': 'v4.3.0'}
    assert mod.advance_fallback_channel(newer, preview)
    assert json.loads(preview.read_text()) == newer
    preview.write_text(json.dumps({**meta, 'versionCode': 40400, 'version': 'v4.4.0-RC1'}))
    before = preview.read_bytes()
    assert not mod.advance_fallback_channel(newer, preview)
    assert preview.read_bytes() == before

print("update metadata tests passed")
