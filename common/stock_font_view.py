"""Request-owned ROM views. Never publish or unmount the live font tree."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import signal
import subprocess
import tempfile
import threading

import stock_inventory_scan as recovery


_LOCAL = threading.local()


def current_view():
    return getattr(_LOCAL, "view", None)


class StockView:
    def __init__(self, parent: Path):
        self.parent = parent
        self.base = None
        self.owned = []
        self.roots = {}
        self.alias_origins = {}

    def recover(self, logical: Path):
        # Only the established partition/fonts hierarchy supports this recovery.
        if len(logical.parts) < 4 or "fonts" not in logical.parts[2:]:
            return None
        font_index = logical.parts.index("fonts", 2)
        root = Path(*logical.parts[:font_index + 1])
        if root not in self.roots:
            if self.base is None:
                self.parent.mkdir(parents=True, exist_ok=True)
                self.base = Path(tempfile.mkdtemp(prefix=".stock-view-", dir=self.parent))
            self.roots[root] = recovery._bind_parent_stock_snapshot(
                root, snapshot_base=self.base, owned_snapshots=self.owned)
        actual = self.roots[root]
        return actual / logical.relative_to(root) if actual is not None else None

    def close(self):
        # No recursive deletion: a failed unmount must never walk ROM contents.
        for path in reversed(self.owned):
            try:
                subprocess.run(["umount", str(path)], timeout=1, check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except (OSError, subprocess.SubprocessError):
                pass
            try:
                if str(path) not in recovery._mount_targets():
                    path.rmdir()
            except OSError:
                pass
        if self.base is not None:
            try:
                self.base.rmdir()
            except OSError:
                pass


@contextmanager
def session(parent: Path):
    existing = current_view()
    if existing is not None:
        yield existing
        return
    view = StockView(parent)
    _LOCAL.view = view
    previous = None
    install_handler = threading.current_thread() is threading.main_thread()
    if install_handler:
        previous = signal.getsignal(signal.SIGTERM)
        def terminate(signum, frame):
            raise SystemExit(128 + signum)
        signal.signal(signal.SIGTERM, terminate)
    try:
        yield view
    finally:
        # Repeated TERM must not interrupt ownership cleanup; SIGKILL still can.
        if install_handler:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        try:
            view.close()
        finally:
            _LOCAL.view = None
            if install_handler:
                signal.signal(signal.SIGTERM, previous)
