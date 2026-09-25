"""Universal Declaration Interpreter (Level 3).

Architectural Principles:
1. Declaration Execution: Reads the JSON schema (tools block) and executes queries against the data.
2. Data Firewall: Automatically intercepts and truncates overly large data arrays to protect LLM context.
"""

import json
import time
from pathlib import Path
from typing import Any

BASE_DIR = Path(__file__).parent
EXPORTS_DIR = BASE_DIR / "exports"

# Record count threshold that triggers automatic export to a file
MAX_RETURN_ITEMS = 15


def _load_json(path: str) -> Any:
    """Load and parse a JSON file from the given path."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _resolve_source(data: dict, source_path: str) -> Any:
    """Resolve a path like 'telemetry[]' into a real target object within the data dictionary."""
    path = source_path.replace("synthetic_telemetry.json -> ", "").strip()
    node: Any = data
    for part in path.replace("[]", "").split("."):
        if part == "":
            continue
        node = node[part]
    return node


def _apply_data_firewall(result_list: list, tool_name: str) -> dict:
    """Protect the LLM context from overflow by dumping large result lists into a JSON export file."""
    EXPORTS_DIR.mkdir(exist_ok=True)
    
    timestamp = int(time.time())
    filename = f"{tool_name}_export_{timestamp}.json"
    filepath = EXPORTS_DIR / filename
    
    filepath.write_text(json.dumps(result_list, ensure_ascii=False, indent=2), encoding="utf-8")
    
    return {
        "status": "exported_to_file",
        "total_records": len(result_list),
        "file_name": filename,
        "file_path": str(filepath.absolute()),
        "instruction_for_llm": f"Found {len(result_list)} records. The list is too long to display directly in chat. Inform the user about total_records and file_name."
    }


def execute_lookup(data: dict, source: str, match_field: str, match_value: Any) -> Any:
    """Perform a lookup operation on a list or dictionary source based on a match field and value."""
    node = _resolve_source(data, source)
    if isinstance(node, list):
        return [rec for rec in node if rec.get(match_field) == match_value]
    if isinstance(node, dict):
        return node.get(match_value)
    raise ValueError(f"Source {source} is neither a list nor a dictionary")


def _is_null(val: Any) -> bool:
    """Check if a value is None, null string, or empty string."""
    return val is None or (isinstance(val, str) and val.lower() in ("null", "none", ""))


OPERATOR_MAP = {
    'gt': 'gt', 'greater_than': 'gt', '>': 'gt',
    'gte': 'gte', 'greater_than_or_equal': 'gte', '>=': 'gte',
    'lt': 'lt', 'less_than': 'lt', '<': 'lt',
    'lte': 'lte', 'less_than_or_equal': 'lte', '<=': 'lte',
    'eq': 'eq', 'equals': 'eq', 'equal': 'eq', '==': 'eq',
    'neq': 'neq', 'not_equals': 'neq', 'not_equal': 'neq', '!=': 'neq'
}


def execute_filter(
    data: dict, 
    source: str, 
    field: str = None, 
    value: Any = None, 
    filters: dict = None, 
    sort_by: str = None, 
    sort_order: str = "desc", 
    top_n: int = None
) -> list:
    """Filter, sort, and slice a dataset based on individual fields or filter dictionaries."""
    node = _resolve_source(data, source)
    if not isinstance(node, list):
        raise ValueError(f"Source {source} must be a list for filtering")

    search_conditions = dict(filters) if filters else {}
    if field is not None:
        search_conditions[field] = value

    results = []
    for rec in node:
        match = True
        for k, v in search_conditions.items():
            rec_value = rec.get(k)
            
            # Handle advanced filter conditions passed as dictionaries by the LLM
            if isinstance(v, dict):
                # Normalize structures like {'condition'/'operator': ..., 'value': ...} into checkable pairs.
                # Support multiple operator aliases explicitly to prevent dropping valid matches.
                if 'condition' in v and 'value' in v:
                    ops_to_check = [(v['condition'], v['value'])]
                elif 'operator' in v and 'value' in v:
                    ops_to_check = [(v['operator'], v['value'])]
                else:
                    ops_to_check = list(v.items())

                for op_raw, op_val in ops_to_check:
                    op = OPERATOR_MAP.get(str(op_raw).lower())

                    if op == 'eq':
                        if _is_null(op_val):
                            if not _is_null(rec_value): match = False
                        elif rec_value != op_val: match = False

                    elif op == 'neq':
                        if _is_null(op_val):
                            if _is_null(rec_value): match = False
                        elif rec_value == op_val: match = False

                    elif op in ('gt', 'gte', 'lt', 'lte'):
                        if _is_null(rec_value) or _is_null(op_val):
                            match = False
                        else:
                            try:
                                rv, ov = float(rec_value), float(op_val)
                                if op == 'gt' and rv <= ov: match = False
                                elif op == 'gte' and rv < ov: match = False
                                elif op == 'lt' and rv >= ov: match = False
                                elif op == 'lte' and rv > ov: match = False
                            except (ValueError, TypeError):
                                match = False
                    else:
                        # Safety fallback: unknown operators invalidate the record match
                        match = False

            # Handle direct equality matching
            else:
                if isinstance(rec_value, list):
                    if v not in rec_value: match = False
                elif _is_null(v):
                    if not _is_null(rec_value): match = False
                elif rec_value != v:
                    try:
                        if float(rec_value) != float(v): match = False
                    except (ValueError, TypeError):
                        match = False

        if match:
            results.append(rec)
            
    # 1. Apply sorting if specified
    if sort_by:
        is_reverse = (sort_order == "desc")
        def safe_sort_key(item):
            val = item.get(sort_by)
            # Push missing values to the very end of the list based on sort direction
            if val is None:
                return float('-inf') if is_reverse else float('inf')
            return val
            
        try:
            results = sorted(results, key=safe_sort_key, reverse=is_reverse)
        except TypeError:
            # Fallback to string comparison if data types are mixed within the sort field
            results = sorted(results, key=lambda x: str(x.get(sort_by) or ""), reverse=is_reverse)

    # 2. Apply limit / slice if specified
    if top_n and isinstance(top_n, int) and top_n > 0:
        results = results[:top_n]

    return results


def execute_count(data: dict, source: str, field: str = None, value: Any = None, filters: dict = None) -> int:
    """Count total records matching the filtering criteria."""
    results = execute_filter(data, source, field=field, value=value, filters=filters)
    return len(results)


def execute_get_all(data: dict, source: str) -> Any:
    """Retrieve all records from the requested source node without modifications."""
    return _resolve_source(data, source)


TOOL_FUNCTIONS = {
    "lookup": execute_lookup,
    "filter": execute_filter,
    "count": execute_count,
    "get_all": execute_get_all,
}


def execute_registry_entry(schema: dict, data: dict, entry_name: str, params: dict) -> Any:
    """Main routing entry point: resolves tool declarations by name and executes them securely."""
    entry = schema.get("tools", {}).get(entry_name)
    if entry is None:
        raise KeyError(f"Registry does not contain a tool definition for '{entry_name}'")

    entry_type = entry["type"]
    result = None

    if entry_type == "static_lookup":
        result = schema 

    elif entry_type in ("lookup", "filter", "count", "get_all"):
        fn = TOOL_FUNCTIONS[entry_type]
        result = fn(data, entry["source"], **params)

    elif entry_type == "function":
        if entry.get("status", "").startswith("NOT_WIRED"):
            raise NotImplementedError(f"Tool '{entry_name}' is marked as NOT_WIRED")
        import importlib.util
        module_path = Path(__file__).parent / entry["source"]
        spec = importlib.util.spec_from_file_location(entry_name, str(module_path))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        result = module.run(data, **params)
    else:
        raise ValueError(f"Unknown registry tool type: {entry_type}")

    # Final pass through the Data Firewall to prevent context window overflow
    if isinstance(result, list) and len(result) > MAX_RETURN_ITEMS:
        return _apply_data_firewall(result, entry_name)

    return result


if __name__ == "__main__":
    schema = _load_json(str(BASE_DIR / "ontology_schema.json"))
    data = _load_json(str(BASE_DIR / "data" / "synthetic_telemetry.json"))
    critical_count = execute_registry_entry(
        schema,
        data,
        "count_sites",
        {"filters": {"solver_priority": "critical"}},
    )
    print(f"Interpreter check passed: {critical_count} critical sites")
