# Validation Report

Status: **passed for the deterministic local pipeline**

Validation date: **2026-09-25**

Dataset: `data/synthetic_telemetry.json` (100 synthetic tower records)

Scope: generator output, ontology tool registry, deterministic interpreter, data firewall, and ten business questions translated from the initial Russian question list. The Mistral conversation loop and self-extension path were also smoke-tested with a controlled local mock; a live API request requires `MISTRAL_API_KEY`.

The values below are synthetic demonstration results. Tool parameters are included so each result can be rerun or independently audited.

## 1. What is the overall statistics of data-quality problems?

Tool: `get_global_summary_report`

Result: 2 towers exceed rated CPH; 8 are missing tank capacity; 17 are missing readings; 14 have fuel above capacity; 50 glitches were filtered; 2 ghost sites; 1 regional mismatch; 30 towers have alarm history. Duplicate IDs, missing coordinates, missing CPH, and efficiency warnings: 0.

## 2. How many towers are currently critical?

Tool: `count_sites`

Parameters: `{"filters": {"solver_priority": "critical"}}`

Result: **72 towers**.

## 3. How many towers are planned?

Tool: `count_sites`

Parameters: `{"filters": {"solver_priority": "planned"}}`

Result: **1 tower**.

## 4. Which towers are ghost sites?

Tool: `get_sites_list`

Parameters: `{"filters": {"data_flags": "ghost_site"}}`

Result: **SITE-0019, SITE-0092**.

## 5. How many towers have missing tank-capacity data?

Tool: `get_global_summary_report`

Result: **8 towers** (`count_missing_capacity`).

## 6. Are there duplicate tower IDs in the accounting data?

Tool: `get_global_summary_report`

Result: **0 duplicate IDs** (`count_duplicate_ids`).

## 7. What discrepancies between accounting and visits were recorded for November 2025?

Tool: `get_regional_accounting_mismatch`

Parameters: `{"field": "month", "value": "2025-11"}`

Result: **No records** in the stored mismatch list for November 2025. The global audit counter reports 1 regional mismatch across the available months, so the month filter should be treated as a validation result rather than proof that all source lists are complete.

## 8. What did accounting report by region for November 2025?

Tool: `get_regional_accounting_summary`

Parameters: `{"match_field": "month", "match_value": "2025-11"}`

| Region | Consumption (L) | Cost (USD) | Delivered (L) | Sites |
|---|---:|---:|---:|---:|
| North Province | 495.3 | 743.0 | 520.1 | 17 |
| East Province | 188.4 | 282.6 | 197.8 | 18 |
| Central District | 152.1 | 228.1 | 159.7 | 23 |
| South Basin | 1071.6 | 1607.4 | 1125.2 | 28 |
| West Highlands | 186.5 | 279.8 | 195.8 | 14 |

## 9. Which five towers have the largest tank capacity?

Tool: `get_top_sites`

Parameters: `{"filters": {}, "sort_by": "total_capacity_liters", "sort_order": "desc", "top_n": 5}`

Result: **SITE-0002, SITE-0003, SITE-0006, SITE-0024, SITE-0028**, each with **2,000 L** capacity.

## 10. Which tower has the highest historical fuel consumption?

Tool: `get_top_sites`

Parameters: `{"filters": {}, "sort_by": "historical_cph", "sort_order": "desc", "top_n": 1}`

Result: **SITE-0059**, Central District, **5.97 CPH**.