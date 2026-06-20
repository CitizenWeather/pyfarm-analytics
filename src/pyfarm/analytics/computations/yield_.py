"""Yield trend computations for pyfarm-analytics.

Note: YieldAnalyzer does NOT query storage directly.
Yield records originate from pyfarm-commerce and are passed in by the caller.
"""

from __future__ import annotations

from pyfarm.analytics.models import YieldRecord


class YieldAnalyzer:
    """Computes yield trends from a list of YieldRecord objects."""

    def compute_trend(self, records: list[YieldRecord]) -> dict:
        """Compute aggregate yield statistics from a set of harvest records.

        Args:
            records: List of YieldRecord instances (may be empty).

        Returns:
            Dictionary with keys:
                - ``avg_weight_g``: mean weight per harvest (float)
                - ``total_yield_g``: sum of all harvested weights (float)
                - ``yield_per_day``:  total yield divided by number of calendar
                  days between the first and last harvest, or 0.0 if ≤1 record.
                - ``record_count``:  number of records used (int)
        """
        if not records:
            return {
                "avg_weight_g": 0.0,
                "total_yield_g": 0.0,
                "yield_per_day": 0.0,
                "record_count": 0,
            }

        weights = [r.weight_g for r in records]
        total = sum(weights)
        avg = total / len(weights)

        # Yield per day — requires at least two distinct harvest dates
        yield_per_day = 0.0
        if len(records) > 1:
            dates = sorted(r.harvested_at for r in records)
            delta_days = (dates[-1] - dates[0]).total_seconds() / 86400
            if delta_days > 0:
                yield_per_day = total / delta_days

        return {
            "avg_weight_g": avg,
            "total_yield_g": total,
            "yield_per_day": yield_per_day,
            "record_count": len(records),
        }

    def yield_per_sqft(self, records: list[YieldRecord], sqft: float) -> float:
        """Compute total yield per square foot of growing area.

        Args:
            records: List of YieldRecord instances.
            sqft:    Growing area in square feet. Must be > 0.

        Returns:
            Total weight in grams divided by sqft; 0.0 if no records or sqft ≤ 0.
        """
        if not records or sqft <= 0:
            return 0.0
        total = sum(r.weight_g for r in records)
        return total / sqft
