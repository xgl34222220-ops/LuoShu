#!/usr/bin/env python3
"""Published-channel rule of stable111_rework_gate: accept only the official
release metadata (or pinned states); reject every other update.json edit."""
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stable111_rework_gate", ROOT / "scripts/stable111_rework_gate.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
pinned = json.loads((ROOT / "scripts/stable111_frozen_runtime.json").read_text())

PROP = "id=LuoShu\nversion=v9.0.0\nversionCode=140000\nversionSeries=refactor\n"
AUTH = "version=v9.0.0\nscope=stable-release\n"
OFFICIAL = {
    "version": "v9.0.0",
    "versionCode": 140000,
    "zipUrl": "https://github.com/xgl34222220-ops/LuoShu/releases/download/refactor-v9.0.0/LuoShu-v9.0.0.zip",
    "changelog": "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/refactor-v9.0.0/RELEASE_NOTES_refactor-v9.0.0.md",
}


def dump(meta):
    return json.dumps(meta, ensure_ascii=False, indent=2) + "\n"


def fixture(directory, *, prop=PROP, auth=AUTH, notes=True, meta=OFFICIAL, text=None):
    root = Path(directory)
    for child in root.iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    (root / "config").mkdir()
    (root / "module.prop").write_text(prop)
    (root / "config/stable_release_authorization.conf").write_text(auth)
    if notes:
        (root / "RELEASE_NOTES_refactor-v9.0.0.md").write_text("notes\n")
    for name in gate.UPDATE_CHANNELS:
        (root / name).write_text(text if text is not None else dump(meta))
    return root


def allowed(root):
    return all(gate.published_channel_allowed(root, name, pinned) for name in gate.UPDATE_CHANNELS)


# The real repository state must pass (this is what sync-update-metadata wrote).
for name in pinned["publishedMetadataSha256"]:
    assert gate.published_channel_allowed(ROOT, name, pinned), name

with tempfile.TemporaryDirectory() as tmp:
    # Accept: exact bytes sync_update_metadata.py publishes for the authorized release.
    assert allowed(fixture(tmp))
    # Accept: pinned v2.2.2 promotion bytes stay allowed regardless of module.prop.
    v222 = {
        "version": "v2.2.2", "versionCode": 70202,
        "zipUrl": "https://github.com/xgl34222220-ops/LuoShu/releases/download/refactor-v2.2.2/LuoShu-v2.2.2.zip",
        "changelog": "https://raw.githubusercontent.com/xgl34222220-ops/LuoShu/refactor-v2.2.2/RELEASE_NOTES_refactor-v2.2.2.md",
    }
    assert allowed(fixture(tmp, meta=v222))

    rejects = {
        "foreign zipUrl": dict(meta={**OFFICIAL, "zipUrl": "https://evil.example/LuoShu-v9.0.0.zip"}),
        "wrong tag in zipUrl": dict(meta={**OFFICIAL, "zipUrl": OFFICIAL["zipUrl"].replace("refactor-v9.0.0/", "refactor-v8.8.8/")}),
        "versionCode mismatch": dict(meta={**OFFICIAL, "versionCode": 140001}),
        "version mismatch": dict(meta={**OFFICIAL, "version": "v9.0.1"}),
        "changelog edited": dict(meta={**OFFICIAL, "changelog": "https://example.com/notes.md"}),
        "extra field": dict(meta={**OFFICIAL, "note": "x"}),
        "reformatted bytes": dict(text=json.dumps(OFFICIAL)),
        "no release authorization": dict(auth="version=v8.8.8\nscope=stable-release\n"),
        "non-stable authorization": dict(auth="version=v9.0.0\nscope=prerelease\n"),
        "missing release notes": dict(notes=False),
        "unknown series": dict(prop=PROP.replace("refactor", "nightly")),
    }
    for label, kwargs in rejects.items():
        assert not allowed(fixture(tmp, **kwargs)), f"must reject: {label}"

print("stable111 published-channel gate tests passed")
