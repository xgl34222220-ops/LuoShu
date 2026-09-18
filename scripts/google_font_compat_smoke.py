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
        details_expanded = False
        for _ in range(8):
            root = self.hierarchy()
            texts = {text for node in root.iter('node') for text in base.labels(node)}
            if any('停用或卸载洛书前' in text for text in texts):
                self.capture('google-font-chinese-help', root)
                return
            if not details_expanded:
                toggles = [
                    node for node in root.iter('node')
                    if node.get('package') == self.package
                    and '详细原理与影响范围' in base.labels(node)
                ]
                if toggles:
                    x, y = base.center(toggles[0])
                    self.adb('shell', 'input', 'tap', str(x), str(y))
                    details_expanded = True
                    time.sleep(.7)
                    continue
            self.scroll(root)
        raise RuntimeError('中文影响与恢复说明不可见或折叠说明无法展开')

    def scroll(self, root):
        rectangles = []
        for node in root.iter('node'):
            if node.get('package') != self.package:
                continue
            try:
                rectangles.append(base.bounds(node))
            except ValueError:
                continue
        if not rectangles:
            raise RuntimeError('无法读取实际 App 页面边界')
        height = max(r[3] for r in rectangles)
        width = max(r[2] for r in rectangles)
        self.adb('shell', 'input', 'swipe', str(width // 2), str(int(height * .72)),
                 str(width // 2), str(int(height * .27)), '400')


if __name__ == '__main__':
    base.SmokeRun = CompatibilitySmokeRun
    raise SystemExit(base.main())
