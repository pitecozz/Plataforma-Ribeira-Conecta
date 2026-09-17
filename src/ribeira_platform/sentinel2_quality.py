"""Central Sentinel-2 L2A Scene Classification Layer policy."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sentinel2QualityPolicy:
    """Conservative, versioned SCL acceptance policy for quantitative NDVI."""

    policy_id: str = "SENTINEL2_SCL_CONSERVATIVE_V1"
    version: int = 1
    accepted_classes: tuple[int, ...] = (4, 5, 6)
    excluded_classes: tuple[int, ...] = (0, 1, 2, 3, 7, 8, 9, 10, 11)
    optional_classes: tuple[int, ...] = (7,)
    scl_asset_key: str = "SCL_20m"

    def accepts(self, values):
        import numpy as np

        return np.isin(values, self.accepted_classes)

    def record(self) -> dict[str, object]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "scl_asset_key": self.scl_asset_key,
            "accepted_classes": list(self.accepted_classes),
            "excluded_classes": list(self.excluded_classes),
            "optional_policy_dependent_classes": list(self.optional_classes),
        }
