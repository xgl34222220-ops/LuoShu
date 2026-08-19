#!/usr/bin/env python3
"""Regression coverage for the batched XML rewrite and target discovery protocols."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "common" / "font_config_overlay.py"
TARGETS = ROOT / "common" / "font_config_targets.py"


def run(*args: object) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *(str(arg) for arg in args)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def rows(text: str) -> list[list[str]]:
    return [line.rstrip("\n").split("\t") for line in text.splitlines() if line.strip()]


with tempfile.TemporaryDirectory(prefix="luoshu batch | ") as tmp_raw:
    tmp = Path(tmp_raw)
    source = tmp / "fonts | config.xml"
    output = tmp / "overlay | generated.xml"
    font_dir = tmp / "font aliases | safe"
    font_dir.mkdir()
    for weight in (400, 500):
        (font_dir / f"LuoShu-{weight}.ttf").write_bytes(b"L" * 2048)

    source.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<familyset>
  <family name="sans-serif"><font weight="400">Roboto-Regular.ttf</font></family>
  <family name="hihonor-sans"><font weight="500">HonorSans-Medium.ttf</font></family>
  <family name="honor-serif-display"><font weight="400">HonorSerif.ttf</font></family>
</familyset>
""",
        encoding="utf-8",
    )

    overlay_jobs = tmp / "overlay jobs.tsv"
    overlay_jobs.write_text(
        f"generate\t{source}\t{output}\t{font_dir}\n"
        f"validate\t{output}\t{font_dir}\n",
        encoding="utf-8",
    )
    result = rows(run(OVERLAY, "--batch", overlay_jobs).stdout)
    assert len(result) == 2, result
    assert result[0][0:5] == ["generate", str(source), "ok", "1", "2"], result[0]
    assert result[1][0:5] == ["validate", str(output), "ok", "0", "2"], result[1]

    tree = ET.parse(output)
    rendered = [
        (family.attrib.get("name", ""), font.text or "")
        for family in tree.getroot().iter("family")
        for font in family.findall("font")
    ]
    assert ("sans-serif", "LuoShu-400.ttf") in rendered, rendered
    assert ("hihonor-sans", "LuoShu-500.ttf") in rendered, rendered
    assert ("honor-serif-display", "HonorSerif.ttf") in rendered, rendered

    # Overlay batching must isolate a broken document and still process later jobs.
    broken = tmp / "broken | fonts.xml"
    broken.write_text("<familyset><broken>", encoding="utf-8")
    mixed_overlay_jobs = tmp / "mixed overlay jobs.tsv"
    mixed_overlay_jobs.write_text(
        f"validate\t{broken}\t\n"
        f"validate\t{source}\t\n",
        encoding="utf-8",
    )
    mixed_overlay = rows(run(OVERLAY, "--batch", mixed_overlay_jobs).stdout)
    assert any(row[:3] == ["validate", str(broken), "error"] for row in mixed_overlay), mixed_overlay
    assert any(row[:3] == ["validate", str(source), "ok"] for row in mixed_overlay), mixed_overlay

    target_jobs = tmp / "target jobs.txt"
    target_jobs.write_text(f"{source}\n", encoding="utf-8")
    discovered = rows(run(TARGETS, "--batch", target_jobs).stdout)
    target_rows = [row for row in discovered if row[0] == "TARGET"]
    doc_rows = [row for row in discovered if row[0] == "DOC"]
    assert [row[2] for row in target_rows] == ["HonorSans-Medium.ttf", "Roboto-Regular.ttf"], target_rows
    assert all(row[2] != "HonorSerif.ttf" for row in target_rows), target_rows
    assert doc_rows == [["DOC", str(source), "ok", "2", ""]], doc_rows

    # Per-document errors must be reported without aborting later documents in the same process.
    mixed_jobs = tmp / "mixed jobs.txt"
    mixed_jobs.write_text(f"{broken}\n{source}\n", encoding="utf-8")
    mixed = rows(run(TARGETS, "--batch", mixed_jobs).stdout)
    assert any(row[:3] == ["DOC", str(broken), "error"] for row in mixed), mixed
    assert any(row[:4] == ["DOC", str(source), "ok", "2"] for row in mixed), mixed

print("Font config batch protocol tests passed.")
