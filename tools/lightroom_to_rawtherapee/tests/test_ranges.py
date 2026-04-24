import unittest

from lr2rt.ranges import clamp_to_value_range, get_value_range, load_default_range_catalog


class RangeCatalogTests(unittest.TestCase):
    def test_load_default_range_catalog_contains_known_keys(self) -> None:
        catalog = load_default_range_catalog()
        compensation = get_value_range(catalog, "Exposure", "Compensation")
        self.assertIsNotNone(compensation)
        assert compensation is not None
        self.assertEqual(compensation.minimum, -5.0)
        self.assertEqual(compensation.maximum, 12.0)
        self.assertEqual(compensation.kind, "float")

        black = get_value_range(catalog, "Exposure", "Black")
        self.assertIsNotNone(black)
        assert black is not None
        self.assertEqual(black.minimum, -16384.0)
        self.assertEqual(black.maximum, 32768.0)

        hl = get_value_range(catalog, "Exposure", "HighlightCompr")
        self.assertIsNotNone(hl)
        assert hl is not None
        self.assertEqual(hl.maximum, 500.0)

        wb_temp = get_value_range(catalog, "White Balance", "Temperature")
        self.assertIsNotNone(wb_temp)
        assert wb_temp is not None
        self.assertEqual(wb_temp.minimum, 1500.0)
        self.assertEqual(wb_temp.maximum, 60000.0)

    def test_clamp_to_value_range(self) -> None:
        catalog = load_default_range_catalog()
        contrast_range = get_value_range(catalog, "Exposure", "Contrast")
        self.assertEqual(clamp_to_value_range(120, contrast_range), 100)
        self.assertEqual(clamp_to_value_range(-140, contrast_range), -100)
        self.assertEqual(clamp_to_value_range(12, contrast_range), 12)


if __name__ == "__main__":
    unittest.main()
