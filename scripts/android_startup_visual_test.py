#!/usr/bin/env python3
"""Synthetic matcher regressions; these never claim emulator acceptance."""
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from android_startup_visual import FrameClassifier, timeline_verdict


class StartupVisualTest(unittest.TestCase):
    def reference(self, theme="light"):
        color = (210, 219, 239) if theme == "light" else (35, 43, 64)
        ink = (20, 25, 35) if theme == "light" else (223, 232, 245)
        home = Image.new("RGB", (360, 780), color)
        draw = ImageDraw.Draw(home)
        draw.rectangle((15, 250, 345, 520), fill=(245, 245, 250) if theme == "light" else (47, 52, 71))
        draw.text((45, 322), "CURRENT FONT", fill=ink)
        draw.text((45, 363), "SYSTEM DEFAULT", fill=ink)
        root = ET.fromstring('''<hierarchy><node text="当前字体" bounds="[43,320][126,337]" />
            <node text="系统默认字体" bounds="[43,361][138,378]" /></hierarchy>''')
        baseline = Image.new("RGB", home.size, (24, 30, 60))
        ImageDraw.Draw(baseline).polygon(((0, 100), (360, 430), (360, 550), (0, 220)), fill=(140, 165, 210))
        classifier = FrameClassifier(home, root, theme, home.size, baseline)
        fixture = Image.open(Path(__file__).with_name("startup_visual_fixtures") / f"native-logo-{theme}.png")
        splash = Image.new("RGB", home.size, fixture.getpixel((0, 0)))
        splash.paste(fixture.resize((168, 168), Image.Resampling.LANCZOS), (96, 306))
        return classifier, home, baseline, splash

    def frames(self, classifier, images):
        return [{"frame": index, "seconds": index * .001,
                 **classifier.classify(np.asarray(image))} for index, image in enumerate(images)]

    def test_real_reference_matches_both_themes_and_single_handoff(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            frames = self.frames(classifier, (baseline, splash, home))
            self.assertEqual([frame["state"] for frame in frames], ["prelaunch", "native-logo", "home"])
            self.assertTrue(timeline_verdict(frames)["passed"])

    def test_old_double_splash_is_rejected_even_when_return_lasts_one_frame(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            frames = self.frames(classifier, (baseline, splash, home, splash, home))
            verdict = timeline_verdict(frames)
            self.assertFalse(verdict["passed"])
            self.assertIn("returned after visible home", " ".join(verdict["errors"]))

    def test_one_black_or_unclassified_frame_is_a_failure(self):
        classifier, home, baseline, splash = self.reference()
        for bad, error in ((Image.new("RGB", home.size, "black"), "Black blank"),
                           (Image.new("RGB", home.size, (240, 241, 244)), "Unclassified")):
            verdict = timeline_verdict(self.frames(classifier, (baseline, splash, home, bad, home)))
            self.assertFalse(verdict["passed"])
            self.assertIn(error, " ".join(verdict["errors"]))

    def test_unrelated_center_grid_cannot_pass_as_the_native_logo(self):
        classifier, home, baseline, splash = self.reference()
        unrelated = Image.new("RGB", home.size, (210, 219, 239))
        draw = ImageDraw.Draw(unrelated)
        for position in (100, 140, 180, 220, 260):
            draw.line((position, 310, position, 470), fill=(50, 70, 100), width=3)
            draw.line((100, position + 210, 260, position + 210), fill=(50, 70, 100), width=3)
        frame = classifier.classify(np.asarray(unrelated))
        self.assertEqual("unclassified", frame["state"])
        self.assertLess(frame["logo_score"], .5)

    def test_warm_resume_requires_no_branding_and_actual_home(self):
        classifier, home, baseline, splash = self.reference()
        self.assertTrue(timeline_verdict(self.frames(classifier, (baseline, home)), warm=True)["passed"])
        self.assertFalse(timeline_verdict(self.frames(classifier, (baseline, splash, home)), warm=True)["passed"])


if __name__ == "__main__":
    unittest.main()
