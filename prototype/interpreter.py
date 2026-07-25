"""
Universal interpreter for tools_registry declarations.

Does not contain domain-specific functions. Contains several universal
operations (lookup / filter / count) that read declarations from
ontology_schema.json -> tools_registry and query telemetry.json directly.

Serves as the execution engine for the Semantic Router layer — the LLM
decides which tools_registry declaration to invoke, and this module executes it.
"""

import json
from pathlib import Path
from typing import Any


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_source(data: dict, source_path: str) -> Any:
    """
    Resolves paths like 'telemetry[]' or
    'audit.regional_report.regional_accounting_mismatch' into actual objects.
    """
    path = source_path.replace("telemetry.json -> ", "").strip()
    node: Any = data
    for part in path.replace("[]", "").split("."):
        if part == "":
            continue
        node = node[part]
    return node


def execute_lookup(
    data: dict, source: str, match_field: str, match_value: Any
) -> Any:
    """Finds one or more objects by exact key-field match."""
    node = _resolve_source(data, source)
    if isinstance(node, list):
        results = [rec for rec in node if rec.get(match_field) == match_value]
        return results
    if isinstance(node, dict):
        return node.get(match_value)
    raise ValueError(f"Source {source} is neither a list nor a dict")


def execute_filter(data: dict, source: str, field: str, value: Any) -> list:
    """Filters a list of records by field value. Supports list containment."""
    node = _resolve_source(data, source)
    if not isinstance(node, list):
        raise ValueError(f"Source {source} must be a list for filter")

    results = []
    for rec in node:
        rec_value = rec.get(field)
        if isinstance(rec_value, list):
            if value in rec_value:
                results.append(rec)
        elif rec_value == value:
            results.append(rec)
    return results


def execute_count(data: dict, source: str, field: str, value: Any) -> int:
    """Counts matching records by field value."""
    results = execute_filter(data, source, field, value)
    return len(results)


TOOL_FUNCTIONS = {
    "lookup": execute_lookup,
    "filter": execute_filter,
    "count": execute_count,
}


def execute_registry_entry(
    schema: dict, data: dict, entry_name: str, params: dict
) -> Any:
    """
    Main entry point: fetches declaration by name from tools_registry,
    determines operation type (lookup/filter/count/function), and executes it.
    """
    entry = schema["tools_registry"].get(entry_name)
    if entry is None:
        raise KeyError(f"Entry '{entry_name}' missing from tools_registry")

    entry_type = entry["type"]

    if entry_type == "static_lookup":
        # Direct read from schema itself (e.g., DataQualityFlag.instances)
        return schema  # Simplified for prototype

    if entry_type in ("lookup", "filter", "count"):
        fn = TOOL_FUNCTIONS[entry_type]
        return fn(data, entry["source"], **params)

    if entry_type == "function":
        if entry.get("status", "").startswith("NOT_WIRED"):
            raise NotImplementedError(
                f"'{entry_name}' marked as NOT_WIRED: {entry.get('status')}"
            )
        # Self-extended tools — implementation resides in tools/<entry_name>.py
        import importlib.util

        module_path = Path(__file__).parent / entry["source"]
        spec = importlib.util.spec_from_file_location(entry_name, module_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run(data, **params)

    raise ValueError(f"Unknown tool type: {entry_type}")


if __name__ == "__main__":
    # Standalone execution check without LLM — verifies interpreter execution.
    # Paths are relative to the file location rather than working directory.
    base_dir = Path(__file__).parent
    schema = _load_json(str(base_dir / "ontology_schema.json"))
    data = _load_json(str(base_dir / "data" / "telemetry.json"))

    critical_sites = execute_registry_entry(
        schema,
        data,
        "get_sites_by_priority",
        {"field": "solver_priority", "value": "critical"},
    )
    print(f"Critical sites count: {len(critical_sites)}")
    print(
        "Sample:", critical_sites[0]["site_id"] if critical_sites else "none"
    )