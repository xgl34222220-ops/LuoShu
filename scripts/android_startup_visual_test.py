#!/usr/bin/env python3
"""Synthetic matcher regressions; these never claim emulator acceptance."""
import unittest
import xml.etree.ElementTree as ET
import io
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image, ImageDraw

from android_startup_visual import FrameClassifier, inspect_recording, original_timestamps, timeline_verdict


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

    def test_cold_without_full_native_logo_has_insufficient_coverage(self):
        classifier, home, baseline, splash = self.reference()
        for frames in (self.frames(classifier, (baseline, home)),
                       [{"frame": 0, "seconds": .01, "state": "logo-transition"},
                        {"frame": 1, "seconds": .02, "state": "home"}]):
            verdict = timeline_verdict(frames)
            self.assertFalse(verdict["passed"])
            self.assertIn("Insufficient cold-start coverage", " ".join(verdict["errors"]))
            self.assertNotIn("returned after visible home", " ".join(verdict["errors"]))
        self.assertTrue(timeline_verdict(self.frames(classifier, (baseline, home)), warm=True)["passed"])


class StartupEvidenceInspectionTest(unittest.TestCase):
    """Fault injection verifies fail-closed evidence handling, not emulator behavior."""

    def test_original_pts_preserve_irregular_frame_intervals(self):
        stamps = ["0", "0.00001", "0.73", "29.99"]
        self.assertEqual([float(stamp) for stamp in stamps],
                         original_timestamps([{"best_effort_timestamp_time": stamp} for stamp in stamps]))

    def test_missing_nonfinite_negative_and_nonincreasing_pts_fail(self):
        for stamps in ([{}], [{"best_effort_timestamp_time": None}],
                       [{"best_effort_timestamp_time": "bad"}],
                       *[[{"best_effort_timestamp_time": stamp}] for stamp in ("nan", "inf", "-inf", "-.01")],
                       [{"best_effort_timestamp_time": "0"}, {"best_effort_timestamp_time": "0"}],
                       [{"best_effort_timestamp_time": "2"}, {"best_effort_timestamp_time": "1"}]):
            with self.subTest(stamps=stamps), self.assertRaises(RuntimeError):
                original_timestamps(stamps)

    def inspect_fault(self, *, probe_error=b"", probe_returncode=0, timestamps=(".01", ".033333"),
                      decoder_error=b"", decoder_returncode=0, byte_adjustment=0):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video, home, hierarchy, output = (root / name for name in ("raw.mp4", "home.png", "home.xml", "verdict.json"))
            video.write_bytes(b"original-video-evidence")
            Image.new("RGB", (360, 780)).save(home)
            hierarchy.write_text("<hierarchy />")
            info = {"streams": [{"width": 720, "height": 1560}],
                    "frames": [{"best_effort_timestamp_time": stamp} for stamp in timestamps]}
            probe = subprocess.CompletedProcess([], probe_returncode, json.dumps(info).encode(), probe_error)
            raw = bytes(360 * 780 * 3 * 2 + byte_adjustment)
            process = Mock(stdout=io.BytesIO(raw), returncode=decoder_returncode)
            process.poll.return_value = decoder_returncode
            process.wait.return_value = decoder_returncode
            classifier = Mock()
            classifier.classify.side_effect = [{"state": "native-logo"}, {"state": "home"}]

            def decode(*args, **kwargs):
                kwargs["stderr"].write(decoder_error)
                return process

            with patch("android_startup_visual.subprocess.run", return_value=probe), \
                 patch("android_startup_visual.subprocess.Popen", side_effect=decode) as decoder, \
                 patch("android_startup_visual.FrameClassifier", return_value=classifier):
                result = inspect_recording(video, home, hierarchy, "light", output)
            self.assertEqual(result, json.loads(output.read_text()))
            return result, decoder.call_count

    def test_every_original_frame_and_pts_reaches_saved_verdict(self):
        result, calls = self.inspect_fault()
        self.assertTrue(result["passed"])
        self.assertEqual(1, calls)
        self.assertEqual(2, result["frames_decoded"])
        self.assertEqual([.01, .033333], [frame["seconds"] for frame in result["frames"]])
        self.assertEqual([0, 1], [frame["frame"] for frame in result["frames"]])

    def test_probe_error_stderr_fails_even_with_zero_exit(self):
        result, calls = self.inspect_fault(probe_error=b"corrupt input packet\n")
        self.assertFalse(result["passed"])
        self.assertEqual(0, calls)
        self.assertIn("corrupt input packet", result["evidence_error"])
        self.assertEqual("corrupt input packet\n", result["probe"]["stderr"])

    def test_decoder_error_stderr_fails_even_with_complete_frames_and_zero_exit(self):
        result, calls = self.inspect_fault(decoder_error=b"invalid NAL unit\n")
        self.assertFalse(result["passed"])
        self.assertEqual(1, calls)
        self.assertEqual(2, result["frames_decoded"])
        self.assertEqual("invalid NAL unit\n", result["decoder"]["stderr"])
        self.assertIn("invalid NAL unit", result["evidence_error"])

    def test_nonzero_probe_and_decoder_exits_fail_and_preserve_evidence(self):
        for kwargs, stage in (({"probe_returncode": 1}, "probe"), ({"decoder_returncode": 1}, "decoder")):
            with self.subTest(stage=stage):
                result, _ = self.inspect_fault(**kwargs)
                self.assertFalse(result["passed"])
                self.assertEqual(1, result[stage]["returncode"])
                self.assertIn("failed", result["evidence_error"])

    def test_truncated_or_extra_decoded_frame_bytes_fail(self):
        for difference in (-1, 1):
            with self.subTest(difference=difference):
                result, _ = self.inspect_fault(byte_adjustment=difference)
                self.assertFalse(result["passed"])
                self.assertIn("original", result["evidence_error"])
                self.assertEqual(1 if difference < 0 else 2, result["frames_decoded"])

    def test_invalid_pts_is_saved_as_failure_before_decode(self):
        result, calls = self.inspect_fault(timestamps=("0", "nan"))
        self.assertFalse(result["passed"])
        self.assertEqual(0, calls)
        self.assertEqual(0, result["frames_decoded"])
        self.assertIn("nonfinite", result["evidence_error"])


if __name__ == "__main__":
    unittest.main()
