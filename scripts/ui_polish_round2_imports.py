#!/usr/bin/env python3
from pathlib import Path

path = Path("android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs/LogsScreenCompact.kt")
text = path.read_text(encoding="utf-8")

if "import androidx.compose.foundation.background\n" not in text:
    anchor = "import androidx.compose.foundation.clickable\n"
    if text.count(anchor) != 1:
        raise SystemExit("background import anchor missing")
    text = text.replace(anchor, "import androidx.compose.foundation.background\n" + anchor, 1)

if "import androidx.compose.foundation.layout.width\n" not in text:
    anchor = "import androidx.compose.foundation.layout.size\n"
    if text.count(anchor) != 1:
        raise SystemExit("width import anchor missing")
    text = text.replace(anchor, anchor + "import androidx.compose.foundation.layout.width\n", 1)

path.write_text(text, encoding="utf-8")
print("task timeline imports added")
