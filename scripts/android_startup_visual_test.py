#!/usr/bin/env python3
"""Synthetic matcher regressions; these never claim emulator acceptance."""
import unittest
import xml.etree.ElementTree as ET
import io
import json
import shutil
import subprocess
import tempfile
import hashlib
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
from PIL import Image, ImageDraw

from android_startup_visual import (SHELL_CARD_BOUNDS, SHELL_TEXT_BOUNDS, FrameClassifier, edges, inspect_recording,
                                    match_score, original_timestamps, timeline_verdict)


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

    def test_shell_fixture_provenance_hashes_and_scope(self):
        folder = Path(__file__).with_name("startup_visual_fixtures")
        provenance = json.loads((folder / "native-shell-provenance.json").read_text())
        self.assertEqual([list(bounds) for bounds in SHELL_TEXT_BOUNDS], provenance["textBounds360x780"])
        self.assertEqual(list(SHELL_CARD_BOUNDS), provenance["cardBounds360x780"])
        kinds = {(x["theme"], x["kind"]) for x in provenance["references"]}
        self.assertEqual({(t, k) for t in ("light", "dark") for k in ("shell", "splash")}, kinds)
        for item in provenance["references"]:
            self.assertEqual(item["sha256"],hashlib.sha256((folder/item["fixture"]).read_bytes()).hexdigest())
            self.assertIn("not home",item["scope"])
            with Image.open(folder / item["fixture"]) as image:
                self.assertEqual((360, 780), image.size)
            if item["origin"] == "emulator":
                self.assertIsInstance(item["runId"], int)
                self.assertGreater(item["ptsSeconds"],0)
            else:
                # Design render used only until the first real emulator recording exists.
                self.assertEqual("design-render", item["origin"])
                self.assertIn("build_launch_assets.py", item["derivation"])

    def shell_reference(self, theme):
        with Image.open(Path(__file__).with_name("startup_visual_fixtures") / f"native-shell-{theme}.png") as image:
            return image.convert("RGB").copy()

    @staticmethod
    def erase(image, bounds, fraction=0.0):
        """Replace (or fade) text with its own local background colour."""
        source = np.asarray(image).astype(np.float32).copy()
        for x1, y1, x2, y2 in bounds:
            crop = source[y1:y2, x1:x2]
            background = np.median(crop.reshape(-1, 3), axis=0)
            source[y1:y2, x1:x2] = background + (crop - background) * fraction
        return Image.fromarray(np.clip(source, 0, 255).astype(np.uint8))

    def test_preparation_shell_is_distinct_from_home_and_requires_both_texts(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            shell = self.shell_reference(theme)
            frames = self.frames(classifier, (baseline, splash, shell, home))
            self.assertEqual([f["state"] for f in frames], ["prelaunch", "native-logo", "startup-shell", "home"])
            self.assertTrue(timeline_verdict(frames)["passed"])
            self.assertFalse(timeline_verdict(frames[:-1])["passed"])
            for missing in SHELL_TEXT_BOUNDS:
                image = self.erase(shell, (missing,))
                self.assertEqual("unclassified", classifier.classify(np.asarray(image))["state"])

    def test_shell_tolerates_drift_and_card_motion_but_not_other_surfaces(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            shell = np.asarray(self.shell_reference(theme)).astype(np.int16)
            drifted = shell.copy()
            drifted[600:740, 200:360] += 9      # accent glow drifting in a corner
            drifted[60:200, 0:150] -= 6
            x1, y1, x2, _ = SHELL_CARD_BOUNDS
            y2 = SHELL_TEXT_BOUNDS[0][1] - 1  # the wordmark never moves with the card
            card = Image.fromarray(np.clip(shell, 0, 255).astype(np.uint8)).crop((x1, y1, x2, y2))
            scaled = Image.fromarray(np.clip(drifted, 0, 255).astype(np.uint8))
            scaled.paste(card.resize((round((x2 - x1) * .955), round((y2 - y1) * .955))),
                         (x1 + round((x2 - x1) * .0225), y1 + round((y2 - y1) * .0225)))
            for image in (np.clip(drifted, 0, 255).astype(np.uint8), np.asarray(scaled)):
                self.assertEqual("startup-shell", classifier.classify(image)["state"])

    def test_shell_cannot_accept_blank_wrong_background_shifted_title_or_extra_content(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            shell = self.shell_reference(theme)
            background = shell.getpixel((180,700))
            variants = [Image.new("RGB", shell.size, background), Image.fromarray(np.roll(np.asarray(shell), 12, axis=1))]
            wrong = shell.copy()
            ImageDraw.Draw(wrong).rectangle((0,130,359,730),fill=(70,80,90))
            variants.append(wrong)
            content = shell.copy()
            ImageDraw.Draw(content).rectangle((40,180,320,500),fill=(180,70,90))
            variants.append(content)
            flat_field = shell.copy()
            ImageDraw.Draw(flat_field).rectangle((0, 47, 359, 497), fill=background)
            ImageDraw.Draw(flat_field).rectangle((0, 564, 359, 733), fill=background)
            variants.append(flat_field)
            for image in variants:
                self.assertEqual("unclassified", classifier.classify(np.asarray(image))["state"])
            self.assertEqual("black-blank",classifier.classify(np.zeros((780,360,3),dtype=np.uint8))["state"])

    def test_nearly_erased_shell_text_cannot_pass_normalized_correlation(self):
        for theme in ("light","dark"):
            classifier, _, _, _ = self.reference(theme)
            shell = self.shell_reference(theme)
            for fraction in (0,.025,.10,.50):
                for bounds in ((SHELL_TEXT_BOUNDS[0],),(SHELL_TEXT_BOUNDS[1],),SHELL_TEXT_BOUNDS):
                    faded = self.erase(shell, bounds, fraction)
                    self.assertEqual("unclassified",classifier.classify(np.asarray(faded))["state"])

    def test_splash_dissolve_and_home_crossfade_are_recognized_transitions(self):
        for theme in ("light", "dark"):
            classifier, home, baseline, splash = self.reference(theme)
            shell = np.asarray(self.shell_reference(theme)).astype(np.float32)
            native = classifier.splash_reference.astype(np.float32)
            target = np.asarray(home).astype(np.float32)
            def mix(first, second, weight):
                return np.clip(first * (1 - weight) + second * weight, 0, 255).astype(np.uint8)
            dissolve = [classifier.classify(mix(native, shell, w))["state"] for w in (.3, .5, .7)]
            crossfade = [classifier.classify(mix(shell, target, w))["state"] for w in (.3, .5, .7)]
            for state in dissolve + crossfade:
                self.assertNotEqual("unclassified", state)
            self.assertIn("shell-transition", dissolve + crossfade)
            sequence = [np.asarray(baseline), np.asarray(splash), mix(native, shell, .5), shell.astype(np.uint8),
                        mix(shell, target, .4), np.asarray(home)]
            frames = [{"frame": i, "seconds": i * .001, **classifier.classify(image)} for i, image in enumerate(sequence)]
            self.assertTrue(timeline_verdict(frames)["passed"], timeline_verdict(frames)["errors"])

    def test_shell_transition_is_forbidden_after_home_warm_or_without_logo(self):
        for frames, warm, error in (
            ([{"state": "native-logo"}, {"state": "home"}, {"state": "shell-transition"}, {"state": "home"}], False, "returned after visible home"),
            ([{"state": "shell-transition"}, {"state": "home"}], True, "Warm same-process"),
            ([{"state": "prelaunch"}, {"state": "shell-transition"}, {"state": "home"}], False, "lacked preceding native-logo"),
        ):
            stamped = [{"frame": i, "seconds": i * .01, **frame} for i, frame in enumerate(frames)]
            result = timeline_verdict(stamped, warm=warm)
            self.assertFalse(result["passed"])
            self.assertIn(error, " ".join(result["errors"]))

    def test_shell_is_forbidden_on_warm_before_logo_and_after_home(self):
        classifier, home, baseline, splash = self.reference()
        shell = self.shell_reference("light")
        cases = [((baseline,splash,shell,home),True,"Warm same-process"),
                 ((baseline,shell,home),False,"preceding native-logo"),
                 ((baseline,splash,home,shell,home),False,"returned after visible home"),
                 ((baseline,splash,shell,splash,home),False,"returned after preparation shell"),
                 ((baseline,splash,shell,baseline,home),False,"previous surface")]
        for images,warm,error in cases:
            result = timeline_verdict(self.frames(classifier,images),warm=warm)
            self.assertFalse(result["passed"])
            self.assertIn(error," ".join(result["errors"]))

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

    def test_two_home_labels_cannot_match_different_translations(self):
        classifier, home, baseline, splash = self.reference()
        altered = home.copy()
        draw = ImageDraw.Draw(altered)
        draw.rectangle((41, 318, 128, 339), fill=(245, 245, 250))
        draw.rectangle((41, 359, 140, 380), fill=(245, 245, 250))
        draw.text((45, 262), "CURRENT FONT", fill=(20, 25, 35))
        draw.text((45, 423), "SYSTEM DEFAULT", fill=(20, 25, 35))
        # Each separate old search can find its text, but no common transform
        # can account for these opposite shifts and altered spacing.
        edge_frame = edges(np.asarray(altered))
        for _, (x1, y1, x2, y2), template in classifier.home_patches:
            self.assertGreaterEqual(match_score(edge_frame[y1:y2, x1:x2], template), .92)
        self.assertEqual("unclassified", classifier.classify(np.asarray(altered))["state"])


class RealSurfaceReferenceTest(unittest.TestCase):
    """Frozen real frame regressions; never evidence a later emulator run passes."""

    @classmethod
    def setUpClass(cls):
        cls.fixtures = Path(__file__).with_name("startup_visual_fixtures")
        cls.provenance = json.loads((cls.fixtures / "surface-reference-provenance.json").read_text())
        cls.classifiers = {}
        for theme in ("light", "dark"):
            with Image.open(cls.fixtures / f"reference-home-{theme}.png") as home:
                cls.classifiers[theme] = FrameClassifier(home,
                    ET.parse(cls.fixtures / f"reference-home-{theme}.xml").getroot(), theme, (360, 780))

    def classify(self, reference):
        with Image.open(self.fixtures / reference["file"]) as original:
            frame = np.asarray(original.convert("RGB").resize((360, 780), Image.Resampling.BILINEAR))
        return self.classifiers[reference["theme"]].classify(frame)

    def test_real_opening_and_resume_transforms_are_explicitly_recognized(self):
        for reference in self.provenance["references"]:
            if reference["expected_state"] not in ("logo-transition", "home-transition"):
                continue
            with self.subTest(file=reference["file"]):
                result = self.classify(reference)
                self.assertEqual(reference["expected_state"], result["state"])
                transform = result["logo_transform" if result["state"] == "logo-transition" else "home_transform"]
                self.assertGreaterEqual(transform["score"], .72)
                self.assertGreaterEqual(transform["scale"], .65)
                self.assertLessEqual(transform["scale"], 1.05)

    def test_real_black_blank_dark_background_and_wrong_launcher_still_fail(self):
        for reference in self.provenance["references"]:
            if reference["expected_state"] not in ("unclassified", "black-blank"):
                continue
            with self.subTest(file=reference["file"]):
                result = self.classify(reference)
                self.assertEqual(reference["expected_state"], result["state"])
                self.assertFalse(timeline_verdict([{"frame": 0, "seconds": reference["time_seconds"], **result}], warm=True)["passed"])

    def test_real_transformed_logo_return_and_warm_branding_fail(self):
        for reference in self.provenance["references"]:
            if reference["expected_state"] != "logo-transition":
                continue
            with self.subTest(file=reference["file"]):
                logo = {"frame": 1, "seconds": .01, **self.classify(reference)}
                home = {"frame": 0, "seconds": 0, "state": "home"}
                final_home = {"frame": 2, "seconds": .02, "state": "home"}
                verdict = timeline_verdict([home, logo, final_home])
                self.assertFalse(verdict["passed"])
                self.assertIn("returned after visible home", " ".join(verdict["errors"]))
                warm = timeline_verdict([logo, final_home], warm=True)
                self.assertFalse(warm["passed"])
                self.assertIn("Warm same-process", " ".join(warm["errors"]))
                self.assertFalse(verdict["native_logo_seen"])

    def test_real_frozen_fixture_hashes_and_original_frame_provenance(self):
        for reference in self.provenance["references"] + self.provenance["home_references"]:
            with self.subTest(file=reference["file"]):
                self.assertEqual(reference["file_sha256"], hashlib.sha256((self.fixtures / reference["file"]).read_bytes()).hexdigest())
                self.assertEqual(64, len(reference["source_sha256"]))
        for reference in self.provenance["references"]:
            self.assertEqual([0, 0, 720, 1560], reference["crop_pixels"])
            self.assertGreaterEqual(reference["frame"], 0)
            self.assertGreaterEqual(reference["time_seconds"], 0)


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

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "Requires real frame decoder tools")
    def test_real_vfr_pts_do_not_round_into_rawvideo_muxer_errors(self):
        # Adjacent frames at 1.000/1.001s expose default low-rate output DTS
        # rounding. Artwork classification is mocked: this is decoder evidence,
        # never an emulator or a synthetic visual-acceptance claim.
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            video, home, hierarchy, output = (root / name for name in ("vfr.mp4", "home.png", "home.xml", "verdict.json"))
            filters = r"settb=1/1000000,setpts=if(eq(N\,0)\,0\,if(eq(N\,1)\,1000000\,if(eq(N\,2)\,1001000\,2000000)))"
            encoded = subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "color=c=red:s=360x780:r=25:d=0.16", "-vf", filters, "-vsync", "0",
                "-enc_time_base", "1/1000000", "-c:v", "libx264", "-bf", "0", "-pix_fmt", "yuv420p", str(video)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            self.assertEqual(b"", encoded.stderr)
            Image.new("RGB", (360, 780)).save(home)
            hierarchy.write_text("<hierarchy />")
            classifier = Mock()
            classifier.classify.side_effect = [{"state": "native-logo"}, *[{"state": "home"}] * 3]
            with patch("android_startup_visual.FrameClassifier", return_value=classifier):
                result = inspect_recording(video, home, hierarchy, "light", output)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(4, result["frames_decoded"])
            self.assertEqual([0, 1, 1.001, 2], [frame["seconds"] for frame in result["frames"]])
            self.assertEqual("", result["decoder"]["stderr"])


if __name__ == "__main__":
    unittest.main()
