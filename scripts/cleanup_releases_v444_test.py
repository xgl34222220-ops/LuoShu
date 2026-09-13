#!/usr/bin/env python3
"""Pure selection and pre-deletion verification tests; never contact GitHub."""
import base64
import json
import unittest
import cleanup_releases_v444 as policy


def release(tag, number, pre=False, date='2026-09-12T00:00:00Z', draft=False):
    return dict(tag_name=tag, id=number, prerelease=pre, published_at=date, draft=draft, assets=[])


class PolicyTest(unittest.TestCase):
    def test_previous_six_keep_v400_and_older_stable(self):
        rows = [release(t, i, 'Beta' in t) for i, t in enumerate(policy.PREVIOUS_SIX)]
        rows += [release('v3.3.6', 100), release(policy.TARGET, 101)]
        self.assertEqual({r['tag_name'] for r in policy.selected(rows)}, policy.PREVIOUS_SIX - {'v4.0.0'})

    def test_all_older_prereleases_but_not_future_or_draft(self):
        rows = [release('v3.3.7-Beta1', 1, True),
                release('v5.0.0-Beta1', 2, True, date='2026-09-14T00:00:00Z'),
                release('v3.0.0-Beta1', 3, True, draft=True)]
        self.assertEqual([r['id'] for r in policy.selected(rows)], [1])

    def test_rerun_does_not_slide_deletion_window(self):
        rows = [release('v4.0.0', 1), release('v3.3.6', 2), release('v3.3.5', 3)]
        self.assertEqual(policy.selected(rows), [])

    def test_preserved_even_when_mislabeled_prerelease(self):
        self.assertEqual(policy.selected([release('v4.0.0', 1, True), release(policy.TARGET, 2, True)]), [])

    def test_missing_timestamp_is_not_deleted(self):
        self.assertEqual(policy.selected([release('v4.3.0', 1, date=None)]), [])

    def test_missing_release_assets_blocks_deletion(self):
        class Client:
            def request(self, _path):
                return release(policy.TARGET, 1)
        with self.assertRaises(RuntimeError):
            policy.verify_published(Client())

    def test_prerelease_cannot_authorize_cleanup(self):
        class Client:
            def request(self, _path):
                return release(policy.TARGET, 1, True)
        with self.assertRaises(RuntimeError):
            policy.verify_published(Client())

    def test_unsynced_update_metadata_blocks_deletion(self):
        target = release(policy.TARGET, 1)
        for name in ('LuoShu-v4.4.4.zip', 'LuoShu-App-v4.4.4.apk'):
            for filename in (name, name + '.sha256'):
                target['assets'].append(dict(name=filename, size=2048, state='uploaded',
                                            digest='sha256:' + 'a' * 64, browser_download_url='download'))
        class Client:
            def request(self, path):
                if path.startswith('releases/'):
                    return target
                return {'content': base64.b64encode(json.dumps({'version': 'v4.3.0'}).encode()).decode()}
        with self.assertRaises(RuntimeError):
            policy.verify_published(Client())


if __name__ == '__main__':
    unittest.main(verbosity=2)
