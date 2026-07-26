import unittest

from PIL import Image
from PySide6.QtCore import QRect

from screen_translator.screen_capture import mask_excluded_regions


class ScreenCaptureTests(unittest.TestCase):
    def test_masks_only_the_overlap_at_display_scale(self) -> None:
        image = Image.new("RGB", (20, 20), (255, 255, 255))
        capture_rect = QRect(100, 200, 10, 10)
        excluded_rect = QRect(104, 203, 3, 3)

        result = mask_excluded_regions(image, capture_rect, [excluded_rect])

        self.assertIs(result, image)
        self.assertEqual(image.getpixel((8, 7)), (0, 0, 0))
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(image.getpixel((14, 14)), (255, 255, 255))

    def test_ignores_excluded_regions_outside_capture(self) -> None:
        image = Image.new("RGB", (10, 10), (12, 34, 56))

        mask_excluded_regions(image, QRect(0, 0, 10, 10), [QRect(20, 20, 5, 5)])

        self.assertEqual(image.getpixel((5, 5)), (12, 34, 56))
