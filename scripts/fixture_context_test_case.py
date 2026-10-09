"""Host fixture contexts with the candidate runner's Python 3.10 API.

Every context registers its own cleanup, preserving LIFO ordering even when
other cleanups are registered between contexts. This helper is never bundled.
"""
from contextlib import ExitStack
import unittest


class FixtureContextTestCase(unittest.TestCase):
    def enterContext(self, context):
        stack = ExitStack()
        value = stack.enter_context(context)
        self.addCleanup(stack.close)
        return value
