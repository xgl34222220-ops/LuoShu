#!/usr/bin/env python3
"""Exercise the real Chinese settings entry on the unrooted UI test emulator.

No fake component state is injected and no enable/restore action is invoked.
Uses the existing screen/crash harness, then inspects the actual nested page.
"""
import time
import android_ui_smoke as base


class CompatibilitySmokeRun(base.SmokeRun):
    def run(self):
        super().run()
        for _ in range(8):
            root = self.hierarchy()
            found = [node for node in root.iter('node')
                     if node.get('package') == self.package and 'Google 字体兼容' in base.labels(node)]
            if found:
                x, y = base.center(found[0])
                self.adb('shell', 'input', 'tap', str(x), str(y))
                break
            self.scroll(root)
        else:
            raise RuntimeError('Google 字体兼容入口不可见')
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            self.assert_running()
            root = self.hierarchy()
            texts = {text for node in root.iter('node') for text in base.labels(node)}
            if {'当前状态', '恢复原设置', '重新检测'}.issubset(texts):
                self.capture('google-font-compatibility', root)
                break
            time.sleep(.3)
        else:
            raise RuntimeError('Google 字体兼容页面未加载')
        # Keep the original real toggle/expanded-help assertion. All stages share
        # one bounded time/gesture budget and retain each actual XML/anchor sample.
        budget = base.ScrollBudget(timeout=90, max_gestures=8)
        root = self.reach_content(
            lambda current: base.visible_action(current, '导出复发诊断', self.package),
            '只读复发诊断入口', budget=budget, root=root,
        )
        # Verify accessibility and enabled state without invoking Root collection.
        self.capture('google-font-diagnostic-entry', root)
        root = self.reach_content(
            lambda current: base.visible_action(current, '详细原理与影响范围', self.package),
            '中文影响与恢复折叠入口', budget=budget, root=root,
        )
        x, y = base.center(base.visible_action(root, '详细原理与影响范围', self.package))
        self.adb('shell', 'input', 'tap', str(x), str(y))
        remaining = budget.deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError('中文影响与恢复说明总时间预算已耗尽')
        root = self.wait_ui(
            lambda current: base.visible_text(current, '收起技术说明', self.package),
            '中文技术说明实际展开', timeout=min(20, remaining),
        )
        root = self.reach_content(
            lambda current: base.visible_text(current, '停用或卸载洛书前', self.package),
            '中文影响与恢复原说明', budget=budget, root=root,
        )
        self.capture('google-font-chinese-help', root)

if __name__ == '__main__':
    base.SmokeRun = CompatibilitySmokeRun
    raise SystemExit(base.main())
