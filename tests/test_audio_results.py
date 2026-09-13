import os
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication

from screen_translator.ui.audio_results import AudioTranslationWindow


class AudioTranslationWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self):
        self.window = AudioTranslationWindow()
        self.window._current_hold_ms = 1200

    def tearDown(self):
        self.window.deleteLater()
        QCoreApplication.processEvents()

    def test_completed_result_has_a_minimum_visible_hold(self):
        self.window.append_result("original", "translation")
        self.assertEqual(len(self.window._history_cards), 0)

        # Arm the hold after the queued editor/layout update.
        QCoreApplication.processEvents()
        self.assertTrue(self.window._current_hold_active)
        self.assertIsNotNone(self.window._current_hold_deadline)

        # A premature/stale timeout must not move the result to history.
        self.window._current_hold_deadline = time.monotonic() + 1.2
        self.window._release_current_hold()
        self.assertEqual(len(self.window._history_cards), 0)

        # Once the explicit deadline has elapsed, the result is archived.
        self.window._current_hold_deadline = time.monotonic() - 0.01
        self.window._release_current_hold()
        self.assertEqual(len(self.window._history_cards), 1)

    def test_placeholder_result_never_enters_history(self):
        self.window.append_result("（无原文）", "translation")
        self.window.append_result("original", "（无译文）")
        QCoreApplication.processEvents()
        self.assertEqual(len(self.window._history_cards), 0)


if __name__ == "__main__":
    unittest.main()
