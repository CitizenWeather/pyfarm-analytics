"""Pydantic models for KPI outputs in pyfarm-analytics."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class YieldRecord(BaseModel):
    """A single harvest yield record."""

    grow_id: str
    crop_type: str
    weight_g: float
    quality_grade: str
    harvested_at: datetime


class EnvironmentSummary(BaseModel):
    """Aggregated environmental KPIs for a grow period."""

    grow_id: str
    stage: str
    period_start: datetime
    period_end: datetime
    mean_temp: float = 0.0
    mean_rh: float = 0.0
    mean_vpd: float = 0.0
    mean_co2: float = 0.0
    dli: float = 0.0  # Daily Light Integral (mol/m²/day)


class NutrientDriftRecord(BaseModel):
    """Tracks drift in a nutrient metric over a period."""

    grow_id: str
    metric: str  # "pH" or "EC"
    start_value: float
    end_value: float
    drift_rate: float  # units/day
    period_days: float
    flagged: bool = False


class AnomalyRecord(BaseModel):
    """A single anomalous sensor reading detected via z-score."""

    grow_id: str
    sensor_id: str
    metric: str
    timestamp: datetime
    value: float
    zscore: float
    threshold: float = 3.0


class KPIDashboard(BaseModel):
    """Full KPI dashboard snapshot for a grow."""

    grow_id: str
    as_of: datetime
    yield_summary: Optional[dict] = Field(default_factory=dict)
    environment_summary: Optional[EnvironmentSummary] = None
    anomalies: list[AnomalyRecord] = Field(default_factory=list)
    nutrient_drifts: list[NutrientDriftRecord] = Field(default_factory=list)
