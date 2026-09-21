from __future__ import annotations

import unittest

import numpy as np

from ribeira_platform.flood_sar import component_metrics, iou, raster_statistics


class FloodSarAnalyticsTests(unittest.TestCase):
    def test_raster_statistics_excludes_nodata_and_reports_percentiles(self) -> None:
        statistics = raster_statistics(
            np.asarray([np.nan, -3.0, -1.0, 1.0, 3.0], dtype="float32")
        )

        self.assertEqual(statistics["count"], 4)
        self.assertEqual(statistics["min"], -3.0)
        self.assertEqual(statistics["median"], 0.0)
        self.assertEqual(statistics["max"], 3.0)

    def test_raster_statistics_rejects_empty_or_constant_distributions(self) -> None:
        with self.assertRaises(ValueError):
            raster_statistics(np.asarray([np.nan, np.nan], dtype="float32"))
        with self.assertRaises(ValueError):
            raster_statistics(np.asarray([1.0, 1.0], dtype="float32"))

    def test_iou_handles_overlap_and_empty_masks(self) -> None:
        self.assertEqual(iou(np.asarray([True, False]), np.asarray([True, True])), 0.5)
        self.assertEqual(iou(np.asarray([False]), np.asarray([False])), 1.0)

    def test_component_metrics_uses_four_connected_components(self) -> None:
        metrics = component_metrics(
            np.asarray(
                [[True, True, False], [False, True, False], [False, False, True]]
            ),
            pixel_area_m2=100.0,
        )

        self.assertEqual(metrics["count"], 2)
        self.assertEqual(metrics["largest_ha"], 0.03)
        self.assertEqual(metrics["median_ha"], 0.02)
