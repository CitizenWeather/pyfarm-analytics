# pyfarm-analytics

KPI computation library for the [pyfarm](https://github.com/pyfarm) ecosystem.

Reads sensor data from `pyfarm-storage` and computes analytics for Phase 2 dashboards: environmental summaries, nutrient drift tracking, z-score anomaly detection, and yield trend analysis.

## Overview

`pyfarm-analytics` is a **pure Python library** — it exposes no HTTP service. It is consumed by:

- **pyfarm-scheduler** — background analytics jobs
- **pyfarm-api** — dashboard route handlers

## Installation

```bash
pip install pyfarm-analytics
```

Development install (with test dependencies):

```bash
pip install -e ".[dev]"
```

## Quick Start

### Using the high-level `Analyzer`

```python
from datetime import datetime, timezone
from pyfarm.storage import get_backend
from pyfarm.analytics import Analyzer

storage = get_backend()
analyzer = Analyzer(storage)

start = datetime(2025, 1, 1, tzinfo=timezone.utc)
end   = datetime(2025, 1, 31, tzinfo=timezone.utc)
grow_id = "grow-001"

# Environment KPIs
summary = await analyzer.environment_summary(grow_id, start, end, stage="vegetative")
print(f"Mean temp: {summary.mean_temp:.1f} °C  DLI: {summary.dli:.2f} mol/m²/day")

# Nutrient drift
drifts = await analyzer.nutrient_drift(grow_id, start, end)
for d in drifts:
    flag = " [FLAGGED]" if d.flagged else ""
    print(f"{d.metric}: {d.drift_rate:+.4f}/day{flag}")

# Anomaly detection
anomalies = await analyzer.anomalies(grow_id, "env", start, end, threshold=3.0)
for a in anomalies:
    print(f"Anomaly: {a.metric}={a.value} z={a.zscore:.2f} @ {a.timestamp}")

# Full dashboard
dashboard = await analyzer.dashboard(grow_id, start, end)
```

### One-liner query helpers

```python
from pyfarm.analytics.queries import get_dashboard, get_anomalies

dashboard = await get_dashboard(grow_id, start, end)
anomalies = await get_anomalies(grow_id, sensor_id="env", start=start, end=end)
```

## Yield Analytics

Yield records originate from `pyfarm-commerce` and are passed in directly (no storage query):

```python
from pyfarm.analytics.computations.yield_ import YieldAnalyzer
from pyfarm.analytics.models import YieldRecord

records = [...]  # List[YieldRecord] from pyfarm-commerce
ya = YieldAnalyzer()

trend = ya.compute_trend(records)
print(f"Total yield: {trend['total_yield_g']}g over {trend['record_count']} harvests")
print(f"Yield per day: {trend['yield_per_day']:.1f} g/day")

grams_per_sqft = ya.yield_per_sqft(records, sqft=50.0)
```

## KPI Models

| Model | Key Fields |
|---|---|
| `EnvironmentSummary` | `mean_temp`, `mean_rh`, `mean_vpd`, `mean_co2`, `dli` |
| `NutrientDriftRecord` | `metric` (pH/EC), `drift_rate`, `flagged` |
| `AnomalyRecord` | `sensor_id`, `metric`, `value`, `zscore`, `threshold` |
| `YieldRecord` | `grow_id`, `crop_type`, `weight_g`, `quality_grade`, `harvested_at` |
| `KPIDashboard` | Aggregates all of the above |

### Drift Thresholds

| Metric | Flag threshold |
|---|---|
| pH | > 0.1 units/day |
| EC | > 0.2 mS/cm/day |

### DLI Estimation

Daily Light Integral (mol/m²/day) is estimated from mean PPFD sensor readings:

```
DLI = mean_PPFD (μmol/m²/s) × photoperiod_hours × 3600 / 1_000_000
```

Default photoperiod assumption: **18 hours/day**.

## Architecture

```
src/pyfarm/analytics/
├── __init__.py           # Public exports
├── models.py             # Pydantic KPI models
├── analyzer.py           # Analyzer class (main entry point)
├── queries.py            # Module-level convenience functions
└── computations/
    ├── environment.py    # EnvironmentAnalyzer: summary + anomaly detection
    ├── nutrients.py      # NutrientAnalyzer: EC/pH drift
    └── yield_.py         # YieldAnalyzer: trend + yield/sqft
```

## Running Tests

```bash
cd /home/user/pyfarm-analytics
python -m pytest tests/ -v
```

## Dependencies

- `pyfarm-core >= 0.1.0` — shared data models (`SensorReading`, `EventKind`, etc.)
- `pyfarm-storage >= 0.1.0` — `StorageBackend` protocol + `get_backend()`
- `pydantic >= 2.0, < 3.0` — model validation
- `numpy >= 1.24, < 2.0` — z-score computation and statistical aggregation
