"""
Synthetic data generator for public demonstration.

Replicates the STRUCTURE of telemetry payload (same keys, field logic,
and audit block) using completely synthetic values. Contains no real
site IDs, regions, or proprietary metrics.
"""

import json
import random
from datetime import datetime, timedelta

# Reproducibility for demo dataset
random.seed(42)

REGIONS = [
    "North Province",
    "East Province",
    "Central District",
    "South Basin",
    "West Highlands",
]
N_SITES = 100  # Default dataset size

FLAG_POOL = [
    "missing_coordinates",
    "ghost_site",
    "cph_exceeds_rated",
    "duplicate_id",
    "missing_cph",
    "missing_capacity",
    "missing_reading",
    "fuel_exceeds_capacity",
    "actual_cph_efficiency_warning",
    "dynamic_cph_efficiency_warning",
]

CURRENT_TIME = datetime(2026, 1, 1)


def make_site(i: int) -> dict:
    site_id = f"SITE-{i:04d}"
    region = random.choice(REGIONS)

    capacity = random.choice([500.0, 1000.0, 1500.0, 2000.0])
    historical_cph = round(random.uniform(1.5, 6.0), 2)
    rated_cph = round(historical_cph * random.uniform(0.8, 1.3), 2)

    # ~15% missing_reading simulation
    has_reading = random.random() > 0.15
    fuel_after = (
        round(random.uniform(0, capacity), 1) if has_reading else None
    )
    last_refuel = CURRENT_TIME - timedelta(days=random.randint(1, 40))

    dynamic_cph = (
        round(historical_cph * random.uniform(0.7, 1.4), 2)
        if has_reading
        else None
    )
    burn_rate = dynamic_cph or historical_cph
    hours_passed = (CURRENT_TIME - last_refuel).total_seconds() / 3600
    current_fuel = (
        max(0, (fuel_after or 0) - hours_passed * burn_rate)
        if has_reading
        else None
    )
    tte_hours = (
        round(current_fuel / burn_rate, 1)
        if has_reading and burn_rate > 0
        else None
    )

    if tte_hours is None:
        priority = None
    elif tte_hours <= 24:
        priority = "critical"
    elif tte_hours <= 72:
        priority = "planned"
    else:
        priority = "nominal"

    flags = []
    if not has_reading:
        flags.append("missing_reading")
    if random.random() < 0.13:
        flags.append("missing_capacity")
    if random.random() < 0.06:
        flags.append("ghost_site")
    if random.random() < 0.04:
        flags.append("cph_exceeds_rated")
    if random.random() < 0.15:
        flags.append("fuel_exceeds_capacity")

    fill_volume = (
        round(max(0, capacity - (current_fuel or 0)), 1)
        if has_reading
        else None
    )

    return {
        "site_id": site_id,
        "data_flags": flags,
        "region": region,
        "lat": round(random.uniform(-5.0, 5.0), 6),
        "lon": round(random.uniform(10.0, 30.0), 6),
        "total_capacity_liters": capacity,
        "historical_cph": historical_cph,
        "rated_cph_max": rated_cph,
        "gensets_count": random.choice([1, 1, 1, 2]),
        "g1_kva": random.choice([20.0, 30.0, 50.0]),
        "g2_kva": 0.0,
        "last_refuel_timestamp": last_refuel.strftime("%Y-%m-%d %H:%M:%S"),
        "fuel_level_after_refuel": fuel_after,
        "current_fuel_estimate": (
            round(current_fuel, 1) if current_fuel is not None else None
        ),
        "actual_cph_last_run": (
            round(burn_rate * random.uniform(0.9, 1.1), 2)
            if has_reading
            else None
        ),
        "dynamic_cph_trend": dynamic_cph,
        "tte_hours": tte_hours,
        "tte_deadline_sec": (
            int(tte_hours * 3600) if tte_hours is not None else None
        ),
        "solver_priority": priority,
        "service_parameters": {
            "base_setup_sec": 900,
            "pump_rate_lps": 1.67,
            "estimated_max_service_time_sec": (
                round(900 + (fill_volume or 0) / 1.67, 0)
                if fill_volume is not None
                else None
            ),
            "fill_volume_l": fill_volume,
        },
        "gensets_detail": [
            {
                "name": "Genset1",
                "capacity_liters": capacity,
                "fuel_before": (
                    round((fuel_after or 0) * 0.3, 1) if has_reading else None
                ),
                "fuel_after": fuel_after,
            }
        ],
    }


def build_audit(sites: list) -> dict:
    ghost = [s["site_id"] for s in sites if "ghost_site" in s["data_flags"]]
    missing_cap = [
        s["site_id"] for s in sites if "missing_capacity" in s["data_flags"]
    ]
    missing_read = [
        s["site_id"] for s in sites if "missing_reading" in s["data_flags"]
    ]
    fuel_exceeds = [
        s["site_id"]
        for s in sites
        if "fuel_exceeds_capacity" in s["data_flags"]
    ]
    cph_exceeds = [
        s["site_id"] for s in sites if "cph_exceeds_rated" in s["data_flags"]
    ]

    months = ["2025-11", "2025-12"]
    regional_calc, regional_acc, mismatch = {}, {}, []
    for month in months:
        regional_calc[month] = {}
        regional_acc[month] = {}
        for region in REGIONS:
            region_sites = [s for s in sites if s["region"] == region]
            calc_l = round(
                sum((s["current_fuel_estimate"] or 0) for s in region_sites)
                * 0.3,
                1,
            )
            acc_l = round(calc_l * random.uniform(0.85, 1.2), 1)
            regional_calc[month][region] = {
                "consumption_l": calc_l,
                "sites_counted": len(region_sites),
            }
            regional_acc[month][region] = {
                "fuel_consumption_qty_l": acc_l,
                "fuel_consumption_cost_usd": round(acc_l * 1.5, 1),
                "fuel_delivered_qty_l": round(acc_l * 1.05, 1),
                "total_sites": len(region_sites),
            }
            deviation = round(abs(acc_l - calc_l) / max(acc_l, 1) * 100, 1)
            if deviation > 15:
                mismatch.append(
                    {
                        "month": month,
                        "region": region,
                        "accounting_qty_l": acc_l,
                        "calculated_qty_l": calc_l,
                        "deviation_pct": deviation,
                        "sites_counted_in_visits": len(region_sites),
                        "sites_expected_by_accounting": len(region_sites),
                        "likely_coverage_gap": False,
                    }
                )

    historical_analytics = {}
    for s in random.sample(sites, k=int(len(sites) * 0.3)):
        historical_analytics[s["site_id"]] = {
            "2025-11": {
                "alarms_count": random.randint(0, 15),
                "total_downtime_hours": round(random.uniform(0, 20), 1),
            }
        }

    return {
        "master_data_issues": {
            "duplicate_ids": [],
            "missing_cph_active": [],
            "missing_cph_orphan": [],
            "cph_exceeds_rated": cph_exceeds,
        },
        "dynamic_data_issues": {
            "sites_missing_capacity": missing_cap,
            "sites_missing_reading": missing_read,
            "sites_missing_coordinates": [],
            "sites_fuel_exceeds_capacity": fuel_exceeds,
            "sites_actual_cph_efficiency_warning": [],
            "sites_dynamic_cph_efficiency_warning": [],
            "telemetry_glitches": {
                "total_visits": 950,
                "valid_visits": 900,
                "glitches_caught": 50,
            },
        },
        "register_data_issues": {
            "ghost_sites": ghost,
            "region_names_normalized": {r: [r] for r in REGIONS},
            "regions_unmatched": [],
            "possible_region_aliases": [],
        },
        "regional_report": {
            "regional_consumption_calculated": regional_calc,
            "regional_accounting_summary": regional_acc,
            "regional_accounting_mismatch": mismatch,
        },
        "historical_analytics": historical_analytics,
        "summary_report": {
            "count_duplicate_ids": 0,
            "count_missing_cph_active": 0,
            "count_missing_cph_orphan": 0,
            "count_cph_exceeds_rated": len(cph_exceeds),
            "count_missing_capacity": len(missing_cap),
            "count_missing_reading": len(missing_read),
            "count_missing_coordinates": 0,
            "count_fuel_exceeds_capacity": len(fuel_exceeds),
            "count_actual_cph_efficiency_warning": 0,
            "count_dynamic_cph_efficiency_warning": 0,
            "count_glitches_found": 50,
            "count_ghost_sites": len(ghost),
            "count_regions_unmatched": 0,
            "count_regional_mismatch": len(mismatch),
            "count_sites_with_alarms": len(historical_analytics),
        },
    }


if __name__ == "__main__":
    sites = [make_site(i) for i in range(1, N_SITES + 1)]
    output = {"telemetry": sites, "audit": build_audit(sites)}
    with open("synthetic_telemetry.json", "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(
        f"Generated {N_SITES} synthetic sites -> synthetic_telemetry.json"
    )
    print(
        f"critical: {sum(1 for s in sites if s['solver_priority'] == 'critical')}"
    )
    print(
        f"planned: {sum(1 for s in sites if s['solver_priority'] == 'planned')}"
    )
    print(
        f"nominal: {sum(1 for s in sites if s['solver_priority'] == 'nominal')}"
    )

```
