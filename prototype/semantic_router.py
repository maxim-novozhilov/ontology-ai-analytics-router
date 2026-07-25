"""
Semantic Router + Meta-Agent (self-extension), Level 3 Prototype.

Requires: pip install mistralai
Requires: MISTRAL_API_KEY environment variable
(Free key: console.mistral.ai -> La Plateforme -> Experiment tier)

Logic:
  1. Build a list of available tools from ontology_schema.json -> tools_registry
     (lookup/filter/count types executed by the universal interpreter)
     + one specialized tool `write_new_tool` for self-extension.
  2. Pass the user's question + this tool list to the model (function calling).
  3. If the model selects an existing lookup/filter/count tool — execute via
     interpreter.py, return the result to the model, and let it formulate
     the final answer.
  4. If the model invokes `write_new_tool` — no pre-declared tool fits the query.
     Write the generated code to tools/<name>.py, append a new entry to
     tools_registry (type: function), execute, and show the result.

Note: Mistral's free tier is rate-limited (few requests per minute).
A pause between consecutive test queries may be required — see time.sleep() in main().
"""

import json
import os
import time
from pathlib import Path

from mistralai import Mistral

from interpreter import execute_registry_entry, _load_json

BASE_DIR = Path(__file__).parent
SCHEMA_PATH = BASE_DIR / "ontology_schema.json"
DATA_PATH = BASE_DIR / "data" / "telemetry.json"
TOOLS_DIR = BASE_DIR / "tools"

MODEL = os.environ.get("ONTOLOGY_MODEL", "mistral-large-latest")


def build_mistral_tools(schema: dict) -> list:
    """Transforms declarative tools_registry entries into function calling format."""

    # Specific field hints to prevent the model from blindly guessing field names
    FIELD_HINTS = {
        "get_site_by_id": {
            "match_field": "Always 'site_id'.",
            "match_value": "The site_id value, e.g., 'SITE-0001'.",
        },
        "get_sites_by_priority": {
            "field": "Always 'solver_priority'.",
            "value": "One of: 'critical', 'planned', 'nominal'.",
        },
        "get_sites_by_flag": {
            "field": "Always 'data_flags'.",
            "value": (
                "One of: missing_coordinates, ghost_site, cph_exceeds_rated, "
                "duplicate_id, missing_cph, missing_capacity, missing_reading, "
                "fuel_exceeds_capacity, actual_cph_efficiency_warning, "
                "dynamic_cph_efficiency_warning."
            ),
        },
    }

    tools = []
    for name, entry in schema["tools_registry"].items():
        if not isinstance(entry, dict):
            continue  # Service fields like "_note" are not tool declarations
        hints = FIELD_HINTS.get(name, {})

        if entry["type"] == "lookup":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": (
                            f"Find record(s) in {entry['source']} by exact key match."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "match_field": {
                                    "type": "string",
                                    "description": hints.get(
                                        "match_field", "key field name"
                                    ),
                                },
                                "match_value": {
                                    "type": "string",
                                    "description": hints.get(
                                        "match_value", "target value"
                                    ),
                                },
                            },
                            "required": ["match_field", "match_value"],
                        },
                    },
                }
            )
        elif entry["type"] == "filter":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": (
                            f"Filter records in {entry['source']} by field value."
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "description": hints.get(
                                        "field", "field name for filtering"
                                    ),
                                },
                                "value": {
                                    "type": "string",
                                    "description": hints.get(
                                        "value", "target value"
                                    ),
                                },
                            },
                            "required": ["field", "value"],
                        },
                    },
                }
            )
        elif entry["type"] == "count":
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": entry.get(
                            "description",
                            f"Count records in {entry['source']} by field value.",
                        ),
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "field": {
                                    "type": "string",
                                    "description": hints.get(
                                        "field",
                                        "field name to check (e.g., solver_priority)",
                                    ),
                                },
                                "value": {
                                    "type": "string",
                                    "description": hints.get(
                                        "value",
                                        "target value (e.g., critical)",
                                    ),
                                },
                            },
                            "required": ["field", "value"],
                        },
                    },
                }
            )

        # Type == function with status NOT_WIRED is intentionally omitted

    # Special tool for self-extension
    tools.append(
        {
            "type": "function",
            "function": {
                "name": "write_new_tool",
                "description": (
                    "Use ONLY if no existing tool can answer the question "
                    "(e.g., aggregation/comparison is needed rather than a simple lookup/filter). "
                    "Writes a new Python function and registers it in the ontology graph."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tool_name": {
                            "type": "string",
                            "description": "snake_case name for the new tool",
                        },
                        "description": {
                            "type": "string",
                            "description": "what the tool does",
                        },
                        "python_code": {
                            "type": "string",
                            "description": (
                                "Complete function code def run(data, **params): ... "
                                "data is the parsed telemetry.json (dict). "
                                "Must return a JSON-serializable result."
                            ),
                        },
                    },
                    "required": ["tool_name", "description", "python_code"],
                },
            },
        }
    )
    return tools


def handle_write_new_tool(
    schema: dict, tool_name: str, description: str, python_code: str
) -> dict:
    """Self-extension: saves code, registers in ontology graph, executes, and returns result."""
    TOOLS_DIR.mkdir(exist_ok=True)
    module_path = TOOLS_DIR / f"{tool_name}.py"
    module_path.write_text(python_code, encoding="utf-8")

    schema["tools_registry"][tool_name] = {
        "type": "function",
        "source": f"tools/{tool_name}.py",
        "description": description,
        "origin": "self_extended",
    }
    SCHEMA_PATH.write_text(
        json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    data = _load_json(str(DATA_PATH))
    result = execute_registry_entry(schema, data, tool_name, {})
    return {"tool_name": tool_name, "registered": True, "result": result}


def ask(question: str) -> str:
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    tools = build_mistral_tools(schema)

    system = (
        "You are a semantic router operating on top of a telecom tower refueling ontology. "
        "You do not have direct access to raw data — only to the tools below attached "
        "to the ontology graph. If no suitable tool exists, use write_new_tool.\n\n"
        "CRITICAL RULE REGARDING NUMBERS: Any number in your response (count of records, "
        "sums, averages, etc.) MUST be taken verbatim from the tool execution output. "
        "Do not paraphrase, round, or recalculate from memory. "
        "If a tool returns a list of N items, the answer must state exactly N "
        "as explicitly calculated (e.g., len() of the list). If uncertain, "
        "explicitly demonstrate the calculation step in your response."
    )

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    for _ in range(4):  # Reflection loop limit
        for attempt in range(5):
            try:
                response = client.chat.complete(
                    model=MODEL,
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                )
                break
            except Exception as exc:
                if "429" in str(exc) or "rate_limited" in str(exc):
                    wait = 20 * (attempt + 1)
                    print(f"  [debug] Rate limit encountered, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        else:
            return "Failed to reach API — rate limit persisted after 5 retries."

        message = response.choices[0].message

        if not message.tool_calls:
            return message.content

        messages.append(message)

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            print(
                f"  [debug] Tool invoked: {call.function.name}, args: {args}"
            )
            try:
                if call.function.name == "write_new_tool":
                    result = handle_write_new_tool(schema, **args)
                else:
                    result = execute_registry_entry(
                        schema, data, call.function.name, args
                    )
                content = json.dumps(
                    result, ensure_ascii=False, default=str
                )[:4000]
                if isinstance(result, list):
                    print(
                        f"  [debug] Result: list containing {len(result)} items"
                    )
                else:
                    print(f"  [debug] Result: {content[:200]}")
            except Exception as exc:  # Prototype sandbox: errors do not crash execution
                content = f"ERROR: {exc}"
                print(f"  [debug] Execution ERROR: {exc}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "name": call.function.name,
                    "content": content,
                }
            )

    return "Reflection loop limit exceeded — escalating to system engineer."


if __name__ == "__main__":
    test_questions = [
        "How many towers are currently in critical priority?",
        "Show site SITE-0001 — what is its priority and region?",
        "Which site is currently consuming the most fuel above its historical average?",
    ]
    for i, q in enumerate(test_questions):
        print("=" * 60)
        print("Question:", q)
        print("Answer:", ask(q))
        if i < len(test_questions) - 1:
            time.sleep(60)  # Free tier rate limit cooldown