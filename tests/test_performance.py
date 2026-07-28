import unittest

from screen_translator.performance import PerformanceStats


class PerformanceStatsTests(unittest.TestCase):
    def test_counters_are_reported(self) -> None:
        stats = PerformanceStats()
        stats.record_ocr()
        stats.record_translation()
        stats.record_translation()

        snapshot = stats.snapshot()

        self.assertEqual(snapshot.ocr_count, 1)
        self.assertEqual(snapshot.translation_count, 2)
