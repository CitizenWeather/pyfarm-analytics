"""Tests for pyfarm-analytics Analyzer using a mock StorageBackend."""

from __future__ import annotations

import sys
import os

# Ensure src layout is on sys.path when running tests directly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
# Also add pyfarm-core and pyfarm-storage source trees
for _pkg in ("pyfarm-core", "pyfarm-storage"):
    _src = os.path.join(
        os.path.dirname(__file__), "..", "..", _pkg, "src"
    )
    if os.path.isdir(_src):
        sys.path.insert(0, _src)

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock

import pytest

from pyfarm.analytics.analyzer import Analyzer
from pyfarm.analytics.computations.yield_ import YieldAnalyzer
from pyfarm.analytics.models import YieldRecord


# ---------------------------------------------------------------------------
# Mock StorageBackend
# ---------------------------------------------------------------------------

def _ts(offset_hours: float = 0) -> datetime:
    """Return a UTC datetime offset from a fixed reference."""
    return datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc) + timedelta(
        hours=offset_hours
    )


def _make_reading(metric: str, value: float, offset_hours: float = 0) -> dict[str, Any]:
    return {
        "metric": metric,
        "value": value,
        "timestamp": _ts(offset_hours),
        "unit": "",
        "sensor_id": "env",
    }


class MockStorageBackend:
    """Minimal mock that satisfies the StorageBackend protocol for tests."""

    def __init__(
        self,
        env_readings: list[dict] | None = None,
        light_readings: list[dict] | None = None,
        nutrient_readings: list[dict] | None = None,
    ):
        self._env = env_readings or []
        self._light = light_readings or []
        self._nutrient = nutrient_readings or []

    async def get_readings(
        self,
        sensor_id: str,
        start_time: datetime,
        end_time: datetime,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        mapping = {
            "env": self._env,
            "light": self._light,
            "nutrient": self._nutrient,
        }
        return mapping.get(sensor_id, [])

    async def get_events(self, *args, **kwargs) -> list:
        return []

    async def get_latest_snapshot(self, grow_id: str) -> dict | None:
        return None

    async def query_timeseries(self, *args, **kwargs) -> list:
        return []

    async def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

START = _ts(0)
END = _ts(24)
GROW_ID = "grow-test-001"


# ---------------------------------------------------------------------------
# environment_summary tests
# ---------------------------------------------------------------------------

class TestEnvironmentSummary:
    """Tests for Analyzer.environment_summary."""

    @pytest.mark.asyncio
    async def test_mean_temp_correct(self):
        """Mean temperature should be the arithmetic mean of all temp readings."""
        readings = [
            _make_reading("temperature", 20.0, 0),
            _make_reading("temperature", 22.0, 1),
            _make_reading("temperature", 24.0, 2),
        ]
        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        summary = await analyzer.environment_summary(GROW_ID, START, END)

        assert summary.grow_id == GROW_ID
        assert abs(summary.mean_temp - 22.0) < 1e-6

    @pytest.mark.asyncio
    async def test_empty_readings_returns_zeros(self):
        """No readings should produce a zero-filled summary rather than raising."""
        storage = MockStorageBackend()
        analyzer = Analyzer(storage)
        summary = await analyzer.environment_summary(GROW_ID, START, END)

        assert summary.mean_temp == 0.0
        assert summary.mean_rh == 0.0
        assert summary.mean_vpd == 0.0
        assert summary.mean_co2 == 0.0
        assert summary.dli == 0.0

    @pytest.mark.asyncio
    async def test_mixed_metrics(self):
        """Mixed metric readings should be separated and averaged correctly."""
        readings = [
            _make_reading("temperature", 21.0, 0),
            _make_reading("temperature", 23.0, 1),
            _make_reading("humidity", 60.0, 0),
            _make_reading("humidity", 70.0, 1),
            _make_reading("co2", 1000.0, 0),
        ]
        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        summary = await analyzer.environment_summary(GROW_ID, START, END)

        assert abs(summary.mean_temp - 22.0) < 1e-6
        assert abs(summary.mean_rh - 65.0) < 1e-6
        assert abs(summary.mean_co2 - 1000.0) < 1e-6

    @pytest.mark.asyncio
    async def test_dli_computed_from_light(self):
        """DLI should be non-zero when PPFD light readings are present."""
        light_readings = [
            {"metric": "ppfd", "value": 500.0, "timestamp": _ts(0), "unit": "μmol/m²/s"},
            {"metric": "ppfd", "value": 600.0, "timestamp": _ts(1), "unit": "μmol/m²/s"},
        ]
        storage = MockStorageBackend(light_readings=light_readings)
        analyzer = Analyzer(storage)
        summary = await analyzer.environment_summary(GROW_ID, START, END)

        # mean_ppfd = 550; DLI = 550 * 18 * 3600 / 1_000_000 = 35.64
        assert summary.dli > 0
        assert abs(summary.dli - 35.64) < 0.01


# ---------------------------------------------------------------------------
# Anomaly detection tests
# ---------------------------------------------------------------------------

class TestAnomalyDetection:
    """Tests for Analyzer.anomalies (z-score detection)."""

    @pytest.mark.asyncio
    async def test_out_of_range_reading_flagged(self):
        """A reading that is far from the mean should be detected as an anomaly."""
        # 29 normal readings + 1 extreme outlier. With population std a single
        # outlier's z-score is bounded by sqrt(n-1), so n must be > 10 for an
        # outlier to exceed a threshold of 3.0.
        readings = [_make_reading("temperature", 22.0, float(i)) for i in range(29)]
        readings.append(_make_reading("temperature", 100.0, 29))  # extreme outlier

        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        anomalies = await analyzer.anomalies(GROW_ID, "env", START, END, threshold=3.0)

        assert len(anomalies) >= 1
        assert any(a.value == 100.0 for a in anomalies)

    @pytest.mark.asyncio
    async def test_no_anomalies_in_uniform_data(self):
        """Uniform readings should produce no anomalies."""
        readings = [_make_reading("temperature", 22.0, float(i)) for i in range(20)]
        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        anomalies = await analyzer.anomalies(GROW_ID, "env", START, END)

        assert anomalies == []

    @pytest.mark.asyncio
    async def test_empty_readings_return_empty_list(self):
        """No readings should return an empty anomaly list."""
        storage = MockStorageBackend()
        analyzer = Analyzer(storage)
        anomalies = await analyzer.anomalies(GROW_ID, "env", START, END)
        assert anomalies == []

    @pytest.mark.asyncio
    async def test_anomaly_record_fields(self):
        """AnomalyRecord should carry correct metadata."""
        # n > 10 required so the single outlier's z-score can exceed 3.0
        # (population-std z-score is bounded by sqrt(n-1)).
        readings = [_make_reading("temperature", 22.0, float(i)) for i in range(29)]
        readings.append(_make_reading("temperature", 200.0, 29))

        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        anomalies = await analyzer.anomalies(
            GROW_ID, "env", START, END, threshold=3.0
        )

        assert len(anomalies) >= 1
        record = next(a for a in anomalies if a.value == 200.0)
        assert record.grow_id == GROW_ID
        assert record.sensor_id == "env"
        assert record.zscore > 3.0
        assert record.threshold == 3.0


# ---------------------------------------------------------------------------
# Nutrient drift tests
# ---------------------------------------------------------------------------

class TestNutrientDrift:
    """Tests for Analyzer.nutrient_drift."""

    @pytest.mark.asyncio
    async def test_ph_drift_detected_and_flagged(self):
        """Rapid pH drift (>0.1/day) should be flagged."""
        # pH rising from 5.5 to 7.5 over 10 days → drift ~0.2/day (threshold: 0.1)
        nutrient_readings = []
        for i in range(11):
            nutrient_readings.append({
                "metric": "ph",
                "value": 5.5 + i * 0.2,
                "timestamp": _ts(i * 24),
                "unit": "pH",
            })

        storage = MockStorageBackend(nutrient_readings=nutrient_readings)
        analyzer = Analyzer(storage)
        drifts = await analyzer.nutrient_drift(GROW_ID, START, _ts(11 * 24))

        ph_drift = next((d for d in drifts if d.metric == "pH"), None)
        assert ph_drift is not None
        assert ph_drift.flagged is True
        assert ph_drift.drift_rate > 0.1

    @pytest.mark.asyncio
    async def test_stable_ph_not_flagged(self):
        """Slow pH drift (<=0.1/day) should not be flagged."""
        # pH rising from 6.0 to 6.5 over 10 days → drift ~0.05/day
        nutrient_readings = []
        for i in range(11):
            nutrient_readings.append({
                "metric": "ph",
                "value": 6.0 + i * 0.05,
                "timestamp": _ts(i * 24),
                "unit": "pH",
            })

        storage = MockStorageBackend(nutrient_readings=nutrient_readings)
        analyzer = Analyzer(storage)
        drifts = await analyzer.nutrient_drift(GROW_ID, START, _ts(11 * 24))

        ph_drift = next((d for d in drifts if d.metric == "pH"), None)
        assert ph_drift is not None
        assert ph_drift.flagged is False

    @pytest.mark.asyncio
    async def test_empty_nutrients_returns_empty(self):
        """No nutrient readings should return an empty list."""
        storage = MockStorageBackend()
        analyzer = Analyzer(storage)
        drifts = await analyzer.nutrient_drift(GROW_ID, START, END)
        assert drifts == []

    @pytest.mark.asyncio
    async def test_ec_drift_flagged(self):
        """EC drift exceeding 0.2/day should be flagged."""
        # EC rising 0.5 per day over 5 days
        nutrient_readings = []
        for i in range(6):
            nutrient_readings.append({
                "metric": "ec",
                "value": 1.0 + i * 0.5,
                "timestamp": _ts(i * 24),
                "unit": "mS/cm",
            })

        storage = MockStorageBackend(nutrient_readings=nutrient_readings)
        analyzer = Analyzer(storage)
        drifts = await analyzer.nutrient_drift(GROW_ID, START, _ts(6 * 24))

        ec_drift = next((d for d in drifts if d.metric == "EC"), None)
        assert ec_drift is not None
        assert ec_drift.flagged is True


# ---------------------------------------------------------------------------
# Yield tests (no storage — pure computation)
# ---------------------------------------------------------------------------

class TestYieldAnalyzer:
    """Tests for YieldAnalyzer (no storage required)."""

    def _make_records(self, weights: list[float], days_apart: float = 1.0) -> list[YieldRecord]:
        base = datetime(2025, 1, 1, tzinfo=timezone.utc)
        return [
            YieldRecord(
                grow_id=GROW_ID,
                crop_type="lettuce",
                weight_g=w,
                quality_grade="A",
                harvested_at=base + timedelta(days=i * days_apart),
            )
            for i, w in enumerate(weights)
        ]

    def test_avg_weight(self):
        ya = YieldAnalyzer()
        records = self._make_records([100.0, 200.0, 300.0])
        trend = ya.compute_trend(records)
        assert abs(trend["avg_weight_g"] - 200.0) < 1e-6

    def test_total_yield(self):
        ya = YieldAnalyzer()
        records = self._make_records([100.0, 200.0, 300.0])
        trend = ya.compute_trend(records)
        assert abs(trend["total_yield_g"] - 600.0) < 1e-6

    def test_yield_per_day(self):
        ya = YieldAnalyzer()
        # 3 harvests each 1 day apart → 2-day span
        records = self._make_records([100.0, 100.0, 100.0], days_apart=1.0)
        trend = ya.compute_trend(records)
        # total=300g over 2 days → 150 g/day
        assert abs(trend["yield_per_day"] - 150.0) < 1e-6

    def test_empty_records(self):
        ya = YieldAnalyzer()
        trend = ya.compute_trend([])
        assert trend["avg_weight_g"] == 0.0
        assert trend["total_yield_g"] == 0.0
        assert trend["yield_per_day"] == 0.0
        assert trend["record_count"] == 0

    def test_yield_per_sqft(self):
        ya = YieldAnalyzer()
        records = self._make_records([500.0, 500.0])
        result = ya.yield_per_sqft(records, sqft=10.0)
        assert abs(result - 100.0) < 1e-6

    def test_yield_per_sqft_zero_sqft(self):
        ya = YieldAnalyzer()
        records = self._make_records([500.0])
        assert ya.yield_per_sqft(records, sqft=0) == 0.0


# ---------------------------------------------------------------------------
# Dashboard integration test
# ---------------------------------------------------------------------------

class TestDashboard:
    """Smoke-test for Analyzer.dashboard."""

    @pytest.mark.asyncio
    async def test_dashboard_structure(self):
        """Dashboard should return a KPIDashboard with all expected fields."""
        readings = [_make_reading("temperature", 22.0, float(i)) for i in range(5)]
        storage = MockStorageBackend(env_readings=readings)
        analyzer = Analyzer(storage)
        dashboard = await analyzer.dashboard(GROW_ID, START, END)

        assert dashboard.grow_id == GROW_ID
        assert dashboard.environment_summary is not None
        assert isinstance(dashboard.anomalies, list)
        assert isinstance(dashboard.nutrient_drifts, list)
        assert isinstance(dashboard.yield_summary, dict)
