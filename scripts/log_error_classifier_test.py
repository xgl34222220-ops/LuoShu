#!/usr/bin/env python3
"""日志错误分类回归：cleanupErrors 等字段名不应被当成错误。"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "android-app/app/src/main/java/io/github/xgl34222220/luoshu/ui/logs"

src = (LOGS / "LogsContract.kt").read_text(encoding="utf-8")
m = re.search(r'LOG_ERROR_PATTERN = "([^"]+)"', src)
assert m, "LOG_ERROR_PATTERN missing"
rx = re.compile(m.group(1), re.IGNORECASE)

screen = (LOGS / "LogsScreenMiuix.kt").read_text(encoding="utf-8")
assert "LogFilter.ERROR -> isLogErrorLine(line)" in screen
assert 'line.contains("error", true)' not in screen
assert 'line.contains("error", ignoreCase = true)' not in src

cleanup = 'TASK-CLEANUP {"cleaned": true, "cleanupErrors": [], "reason": "completed", "result": 0}'
cases = {
    cleanup: False,
    "[MIX-PHASE] phase=wait_child_cleanup event=end result=ok": False,
    "ERROR: mount failed": True,
    "[mix] failed to build composite": True,
    "3 errors while scanning": True,
    "error=timeout": True,
    "字体应用失败": True,
    "发生错误": True,
    "terror_mode=1": False,
}
for line, want in cases.items():
    got = bool(rx.search(line))
    assert got == want, (line, got, want)

diag = (LOGS / "DiagnosticExportUi.kt").read_text(encoding="utf-8")
gm = re.search(r"errorCount=.*?grep -Eic '([^']+)'", diag)
assert gm, "diagnostic grep missing"
pat = gm.group(1)
data = "\n".join(cases) + "\n"
out = subprocess.run(["grep", "-Eic", pat], input=data.encode(), capture_output=True).stdout.decode().strip()
assert out == str(sum(cases.values())), (out, pat)
print("log_error_classifier_test: %d cases OK" % len(cases))
