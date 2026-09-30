#!/usr/bin/env python3
"""Sanitized language/script regressions; no device fonts or diagnostics."""
from pathlib import Path
import sys
import unittest
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'common'), str(ROOT / 'scripts')]
import font_role_shadow as roles
from font_role_shadow_test import slot


class ScriptRoleTest(unittest.TestCase):
    def classified(self, name, lang='', *, latin=True, digits=True, families=None):
        return roles._classification('/system/fonts/' + name,
            slot(name, families or ['fallback'], latin=latin, digits=digits, xml_lang=lang))

    def test_script_subtags_are_not_language_prefixes(self):
        for tag in ('und-Ital', 'und-Plrd', 'rhg-Rohg', 'ro-Rohg', 'en-Cyrl', 'und-Xxxx'):
            with self.subTest(tag=tag):
                self.assertEqual(roles._language_kind([tag]), 'special')
                result = self.classified('SyntheticFallback.ttf', tag)
                self.assertEqual(result['role'], 'special-fallback')
                self.assertEqual(result['action'], 'preserve')

    def test_script_names_preserved_without_language(self):
        for name in ('NotoSansOldItalic-Regular.ttf', 'NotoSansMiao-Regular.otf',
                     'NotoSansHanifiRohingya-Regular.otf'):
            for lang in ('', 'en'):
                with self.subTest(name=name, lang=lang):
                    self.assertEqual(self.classified(name, lang)['role'], 'special-fallback')

    def test_digit_compatibility_does_not_override_special_script(self):
        result = self.classified('SyntheticScript.ttf', 'und-Plrd', latin=False, digits=True)
        self.assertEqual(result['role'], 'special-fallback')
        self.assertEqual(result['action'], 'preserve')

    def test_supported_language_and_script_positive_controls(self):
        for tag in ('it', 'pl', 'ro', 'en-US', 'und-Latn', 'en-Latn-US', 'fr-CA', 'en-u-ca-gregory'):
            with self.subTest(tag=tag):
                self.assertEqual(roles._language_kind([tag]), 'latin')
        for tag in ('zh-Hans', 'zh-Hant-TW', 'cmn-Hans-CN', 'yue-Hant', 'und-Hani'):
            self.assertEqual(roles._language_kind([tag]), 'cjk')
        self.assertEqual(roles._language_kind(['en-Latn, und-Plrd']), 'special')
        self.assertEqual(roles._language_kind(['en-Latn', 'rhg-Rohg']), 'special')
        self.assertEqual(roles._language_kind(['en-x-Ital']), 'latin')

    def test_normal_noto_latin_and_real_italic_are_not_blanket_protected(self):
        for name in ('NotoSans-Regular.ttf', 'NotoSans-Italic.ttf', 'SourceSansPro-Italic.ttf'):
            result = self.classified(name, 'en')
            self.assertEqual(result['role'], 'latin')
            self.assertEqual(result['action'], 'conditional')
        self.assertEqual(self.classified('Roboto-Regular.ttf', families=['sans-serif'])['role'], 'ui-sans')

    def test_explicit_generic_typography_is_preserved_without_filename_heuristic(self):
        for family in ('cursive', 'casual', 'fantasy'):
            result = self.classified('ArbitraryFont.ttf', families=[family])
            self.assertEqual(result['role'], 'special-fallback')
            self.assertIn('explicit-decorative-family', result['reasons'])
        # A decorative alias is not permission to abandon a shared UI family.
        result = self.classified('ArbitraryFont.ttf', families=['cursive', 'sans-serif'])
        self.assertEqual(result['role'], 'ui-sans')
        self.assertNotEqual(self.classified('DancingScript-Regular.ttf', families=['sans-serif'])['role'], 'special-fallback')
        self.assertNotEqual(self.classified('ComingSoon.ttf', families=['sans-serif'])['role'], 'special-fallback')

    def test_old_cached_role_revision_is_rejected(self):
        with self.assertRaises(roles.RoleError):
            roles.validate_role_map({'schema': roles.ROLE_SCHEMA, 'state': 'ready', 'roleRevision': 1})


if __name__ == '__main__':
    unittest.main(verbosity=2)
