#!/usr/bin/env python3
"""A finished reconciliation has no watcher; a later explicit call still repairs."""
import unittest
import google_font_provider_lifecycle_test as fixtures


class ExplicitReconcileTest(unittest.TestCase):
    setUp = fixtures.ProviderLifecycleTest.setUp
    command = fixtures.ProviderLifecycleTest.command
    bridge = fixtures.ProviderLifecycleTest.bridge
    rows = fixtures.ProviderLifecycleTest.rows
    run_service = fixtures.ProviderLifecycleTest.run_service
    assert_clean = fixtures.ProviderLifecycleTest.assert_clean
    def test_later_explicit_apply_handles_new_selection_after_default_pass(self):
        self.active.write_text('default\n')
        first = self.run_service('reconcile')
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(self.rows('restored'), ['restored'])
        self.assertEqual(self.rows('applied'), [])
        self.active.write_text('custom\n')
        second = self.run_service('reconcile')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.rows('applied'), ['applied'])
        self.assertEqual(self.rows('sleeps'), [])

    def test_same_selection_can_be_reconciled_again_without_a_resident_service(self):
        self.assertEqual(self.run_service('reconcile').returncode, 0)
        self.assertEqual(self.run_service('reconcile').returncode, 0)
        self.assertEqual(self.rows('applied'), ['applied', 'applied'])
        self.assertEqual(self.rows('fingerprints'), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
