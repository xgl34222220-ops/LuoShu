#!/usr/bin/env python3
"""customize.sh sources the frozen v2.2.7 installer after rewriting only its
stand-alone `exit 0` / `exit 1` lines into `return`. APatch sources
customize.sh, so any other exit form (`|| exit 1`, `exit 2`, `exit $rc`, ...)
would leave the manager's install shell before the old private view is
unmounted. Guard that the frozen installer never grows such a form, using the
exact sed expressions customize.sh runs."""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CUSTOMIZE = ROOT / "customize.sh"
V227 = ROOT / ".luoshu-runtime/compat/v227/customize.sh"
EXIT_WORD = re.compile(r"(^|[^A-Za-z0-9_$.-])exit\b")


def sed_expressions() -> list[str]:
    text = CUSTOMIZE.read_text(encoding="utf-8")
    block = re.search(r"^sed (-e '.*?)\s+\"\$_lc_base\"", text, re.S | re.M)
    assert block, "customize.sh no longer rewrites the delegated installer with sed"
    expressions = re.findall(r"-e '([^']*)'", block.group(1))
    assert len(expressions) == 2, expressions
    return expressions


def rewrite(source: str) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False, encoding="utf-8") as handle:
        handle.write(source)
        path = handle.name
    try:
        args = ["sed"]
        for expression in sed_expressions():
            args += ["-e", expression]
        return subprocess.run(args + [path], check=True, capture_output=True, text=True).stdout
    finally:
        Path(path).unlink()


def remaining_exits(script: str) -> list[str]:
    found = []
    for number, line in enumerate(script.splitlines(), 1):
        code = line.split("#", 1)[0]
        if EXIT_WORD.search(code):
            found.append(f"{number}: {line.strip()}")
    return found


def main() -> int:
    # The checker itself must catch every unsafe form.
    for unsafe in ("foo || exit 1", "exit 2", 'exit "$rc"', "  [ -f x ] && exit 0", "exit"):
        assert remaining_exits(rewrite(unsafe + "\n")), unsafe
    for safe in ("exit 0", "    exit 1", "# exit 1 in a comment", "echo exited"):
        assert not remaining_exits(rewrite(safe + "\n")), safe

    rewritten = rewrite(V227.read_text(encoding="utf-8"))
    leftovers = remaining_exits(rewritten)
    if leftovers:
        print("v2.2.7 customize.sh has exit forms customize.sh does not rewrite:", file=sys.stderr)
        print("\n".join(leftovers), file=sys.stderr)
        return 1
    assert "return 0" in rewritten
    print("customize.sh exit rewrite regression passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
