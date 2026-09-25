import json
import unittest
from pathlib import Path

from interpreter import execute_registry_entry


ROOT = Path(__file__).resolve().parents[1]


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "ontology_schema.json").read_text())
        cls.data = json.loads(
            (ROOT / "data" / "synthetic_telemetry.json").read_text()
        )

    def test_dataset_and_registry_contract(self):
        self.assertEqual(len(self.data["telemetry"]), 100)
        self.assertEqual(
            set(self.schema["tools"]),
            {
                "get_site_summary",
                "get_regional_accounting_mismatch",
                "get_regional_consumption_calculated",
                "get_regional_accounting_summary",
                "get_site_historical_analytics",
                "get_global_summary_report",
                "count_sites",
                "get_sites_list",
                "get_top_sites",
            },
        )

    def test_documented_business_results(self):
        summary = execute_registry_entry(
            self.schema, self.data, "get_global_summary_report", {}
        )
        self.assertEqual(summary["count_missing_capacity"], 8)
        self.assertEqual(summary["count_missing_reading"], 17)
        self.assertEqual(summary["count_ghost_sites"], 2)
        self.assertEqual(summary["count_regional_mismatch"], 1)

        self.assertEqual(
            execute_registry_entry(
                self.schema,
                self.data,
                "count_sites",
                {"filters": {"solver_priority": "critical"}},
            ),
            72,
        )
        self.assertEqual(
            execute_registry_entry(
                self.schema,
                self.data,
                "count_sites",
                {"filters": {"solver_priority": "planned"}},
            ),
            1,
        )

        ghosts = execute_registry_entry(
            self.schema,
            self.data,
            "get_sites_list",
            {"filters": {"data_flags": "ghost_site"}},
        )
        self.assertEqual(
            [site["site_id"] for site in ghosts],
            ["SITE-0019", "SITE-0092"],
        )

        mismatch = execute_registry_entry(
            self.schema,
            self.data,
            "get_regional_accounting_mismatch",
            {"field": "month", "value": "2025-11"},
        )
        self.assertEqual(mismatch, [])

        accounting = execute_registry_entry(
            self.schema,
            self.data,
            "get_regional_accounting_summary",
            {"match_field": "month", "match_value": "2025-11"},
        )
        self.assertEqual(
            accounting["South Basin"]["fuel_consumption_qty_l"], 1071.6
        )

        top_capacity = execute_registry_entry(
            self.schema,
            self.data,
            "get_top_sites",
            {
                "filters": {},
                "sort_by": "total_capacity_liters",
                "sort_order": "desc",
                "top_n": 5,
            },
        )
        self.assertEqual(
            [site["site_id"] for site in top_capacity],
            ["SITE-0002", "SITE-0003", "SITE-0006", "SITE-0024", "SITE-0028"],
        )

        top_cph = execute_registry_entry(
            self.schema,
            self.data,
            "get_top_sites",
            {
                "filters": {},
                "sort_by": "historical_cph",
                "sort_order": "desc",
                "top_n": 1,
            },
        )
        self.assertEqual(top_cph[0]["site_id"], "SITE-0059")
        self.assertEqual(top_cph[0]["historical_cph"], 5.97)

    def test_data_firewall_exports_large_result(self):
        result = execute_registry_entry(
            self.schema, self.data, "get_sites_list", {"filters": {}}
        )
        self.assertEqual(result["status"], "exported_to_file")
        self.assertEqual(result["total_records"], 100)
        export_path = Path(result["file_path"])
        self.assertTrue(export_path.exists())
        self.addCleanup(export_path.unlink, missing_ok=True)


if __name__ == "__main__":
    unittest.main()