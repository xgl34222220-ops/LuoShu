#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "common" / "font_config_targets.py"


def main() -> int:
    xml = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="utf-8"?>
        <familyset>
          <family name="sans-serif">
            <font weight="400">Roboto-Regular.ttf</font>
            <font weight="700">Roboto-Bold.ttf</font>
            <font weight="400" style="italic">Roboto-Italic.ttf</font>
          </family>
          <family name="Oplus-Sans">
            <font weight="350">OPSans-Regular.ttf</font>
          </family>
          <family name="Honor-Sans">
            <font weight="500">HONORSans-Medium.ttf</font>
          </family>
          <family name="vivo Sans">
            <font weight="400">vivoSansVF.ttf</font>
          </family>
          <family name="FlymeFont">
            <font weight="500">FlymeSans-Medium.ttf</font>
          </family>
          <family name="sans-serif" lang="ja">
            <font weight="400">NotoSansCJKjp-Regular.otf</font>
          </family>
          <family name="sans-serif-monospace">
            <font weight="400">RobotoMono-Regular.ttf</font>
          </family>
          <family name="emoji">
            <font weight="400">NotoColorEmoji.ttf</font>
          </family>
          <family>
            <font weight="400">NotoSansFallback.ttf</font>
          </family>
        </familyset>
        """
    )
    with tempfile.TemporaryDirectory() as temporary:
        path = Path(temporary) / "fonts.xml"
        path.write_text(xml, encoding="utf-8")
        result = subprocess.run(
            ["python3", str(TOOL), "--input", str(path)],
            check=True,
            text=True,
            capture_output=True,
        )
    lines = {line.split("|", 2)[0]: line for line in result.stdout.splitlines() if line}
    assert lines["Roboto-Regular.ttf"].split("|")[1] == "400"
    assert lines["Roboto-Bold.ttf"].split("|")[1] == "700"
    assert lines["OPSans-Regular.ttf"].split("|")[1] == "300"
    assert lines["HONORSans-Medium.ttf"].split("|")[1] == "500"
    assert lines["vivoSansVF.ttf"].split("|")[1] == "400"
    assert lines["FlymeSans-Medium.ttf"].split("|")[1] == "500"
    for protected in (
        "Roboto-Italic.ttf",
        "NotoSansCJKjp-Regular.otf",
        "RobotoMono-Regular.ttf",
        "NotoColorEmoji.ttf",
        "NotoSansFallback.ttf",
    ):
        assert protected not in lines, protected
    print("font config target discovery tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
