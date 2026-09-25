"""
Semantic Router (Single-Role Prototype), Level 3.

Requires: pip install mistralai
Requires environment variable: MISTRAL_API_KEY
"""

import json
import os
import time
from pathlib import Path

from mistralai import Mistral

from interpreter import execute_registry_entry, _load_json

BASE_DIR = Path(__file__).parent
SCHEMA_PATH = BASE_DIR / "ontology_schema.json"
DATA_PATH = BASE_DIR / "data" / "synthetic_telemetry.json"
TOOLS_DIR = BASE_DIR / "tools"
LOG_PATH = BASE_DIR / "suggested_tools.json"

MODEL = os.environ.get("ONTOLOGY_MODEL", "mistral-large-latest")


def build_mistral_tools(schema: dict) -> list:
    """Convert declarative schema entries into Mistral function calling format."""
    tools = []
    entities = schema.get("entities", {})
    
    for name, entry in schema.get("tools", {}).items():
        if not isinstance(entry, dict) or "type" not in entry:
            continue
            
        base_desc = entry.get("description", f"Выполнить {entry['type']} в источнике {entry.get('source')}")
        properties = {}
        required_fields = []
        schema_params = entry.get("parameters", {})
        target_entity = entry.get("target_entity")
        
        if entry["type"] == "get_all":
            # get_all does not accept any parameters.
            # execute_get_all(data, source) has no **kwargs, so the parameter schema is always empty.
            pass
        
        elif not schema_params and entry["type"] in ["lookup", "filter", "count", "get_all"]:
            key_field = "match_field" if entry["type"] == "lookup" else "field"
            val_field = "match_value" if entry["type"] == "lookup" else "value"
            
            properties = {
                key_field: {"type": "string", "description": "имя поля-ключа"},
                val_field: {"type": "string", "description": "искомое значение"}
            }
            required_fields = [key_field, val_field]
        else:
            for param_name, param_data in schema_params.items():
                prop = {
                    "type": param_data.get("type", "string"),
                    "description": param_data.get("description", "")
                }
                if "enum" in param_data:
                    prop["enum"] = param_data["enum"]
                
                # Dynamically pull fields from the associated entity in the graph for the 'filters' parameter
                if param_name == "filters" and target_entity and target_entity in entities:
                    entity_props = entities[target_entity].get("properties", [])
                    filter_properties = {}
                    
                    for p in entity_props:
                        p_name = p.get("name")
                        p_type = p.get("type", "string")
                        p_desc = p.get("description", "")
                        
                        json_type = "number" if p_type in ("float", "integer") else "string"
                        field_schema = {
                            "type": json_type,
                            "description": p_desc
                        }
                        
                        # Domain constraints (e.g., allowed enum values) live on the entity itself.
                        # We inject them here to avoid duplicating data in the tools block.
                        if "enum" in p:
                            field_schema["enum"] = p["enum"]
                            if "enum_descriptions" in p:
                                mapping = "\nЗначения флагов:\n" + "\n".join(
                                    [f"- {k}: {v}" for k, v in p["enum_descriptions"].items()]
                                )
                                field_schema["description"] += mapping

                        filter_properties[p_name] = field_schema
                    
                    prop["properties"] = filter_properties
                    prop["additionalProperties"] = False

                properties[param_name] = prop
                required_fields.append(param_name)

        if entry["type"] in ["lookup", "filter", "count", "get_all"]:
            tools.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": base_desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required_fields,
                    },
                },
            })

    # Append the dynamic self-extension tool
    tools.append({
        "type": "function",
        "function": {
            "name": "write_new_tool",
            "description": (
                "Использовать, ТОЛЬКО если ни один существующий инструмент не может ответить "
                "на вопрос. Пишет новую Python-функцию для разового исполнения."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "snake_case имя нового инструмента"},
                    "description": {"type": "string", "description": "что делает инструмент"},
                    "python_code": {
                        "type": "string",
                        "description": (
                            "Полный код функции def run(data, **params): ... "
                            "data — это распарсенный synthetic_telemetry.json (dict). "
                            "РЕАЛЬНАЯ СТРУКТУРА data (это НЕ имена сущностей графа!): "
                            "data['telemetry'] — список вышек; data['audit'] — вложенные агрегаты "
                            "(master_data_issues, dynamic_data_issues, register_data_issues, regional_report, "
                            "historical_analytics, summary_report). "
                            "НИКОГДА не используй data['Site'] или другие имена сущностей графа как ключи в data. "
                            "КРИТИЧЕСКОЕ ПРАВИЛО 1: Возвращай ТОЛЬКО агрегированные данные. "
                            "КРИТИЧЕСКОЕ ПРАВИЛО 2: НИКОГДА не читай файлы с диска (никаких open() и file_path). "
                            "Твой код должен быть независимым и актуальным, работай СТРОГО с переданным словарем data."
                        ),
                    },
                },
                "required": ["tool_name", "description", "python_code"],
            },
        },
    })
    
    return tools


def handle_write_new_tool(schema: dict, question: str, tool_name: str, description: str, python_code: str) -> dict:
    """Self-extension via quarantine (safe execution of generated code in memory)."""

    # === EXPORT GARBAGE COLLECTION BLOCK ===
    exports_dir = BASE_DIR / "exports"
    if exports_dir.exists():
        current_time = time.time()
        # Iterate through all generated export files
        for file_path in exports_dir.glob("*_export_*.json"):
            # If the file was created less than 60 seconds ago, delete it
            if current_time - file_path.stat().st_mtime < 60:
                try:
                    file_path.unlink()
                    print(f"  [debug] Очистка: удалён файл {file_path.name}")
                except OSError:
                    pass
    # =======================================

    TOOLS_DIR.mkdir(exist_ok=True)
    module_path = TOOLS_DIR / f"{tool_name}.py"
    
    module_path.write_text(python_code, encoding="utf-8")

    if "tools" not in schema:
        schema["tools"] = {}
        
    schema["tools"][tool_name] = {
        "type": "function",
        "source": f"tools/{tool_name}.py",
        "description": description,
        "origin": "ephemeral_quarantine",
    }

    log_entry = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trigger_question": question,
        "tool_name": tool_name,
        "description": description,
        "python_code": python_code
    }
    
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    data = _load_json(str(DATA_PATH))
    try:
        result = execute_registry_entry(schema, data, tool_name, {})
        return {"tool_name": tool_name, "status": "executed_in_quarantine", "result": result}
    except Exception as e:
        return {"tool_name": tool_name, "status": "failed", "error": str(e)}


def ask(question: str) -> str:
    """Main routing function: handles user queries, API interactions, and tool executions."""
    client = Mistral(api_key=os.environ["MISTRAL_API_KEY"])
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    tools = build_mistral_tools(schema)

    # Compile a brief summary of entities and their properties for the system prompt
    entities_summary = {}
    for ent_name, ent_data in schema.get("entities", {}).items():
        if not isinstance(ent_data, dict):
            continue
        if "properties" in ent_data and isinstance(ent_data["properties"], list):
            props = [p.get("name") for p in ent_data["properties"] if isinstance(p, dict)]
        else:
            props = [ent_data.get("type", "object")]
        entities_summary[ent_name] = props

    system = (
        "Ты — семантический маршрутизатор логистической системы. "
        "Твоя задача — подбирать инструменты из реестра для ответа на вопросы.\n\n"
        "ЖЕСТКИЕ ПРАВИЛА:\n"
        "1. ВСЕГДА в первую очередь ищи готовый инструмент в реестре (lookup, filter, count).\n"
        "2. Инструмент 'write_new_tool' разрешено вызывать ТОЛЬКО если задача требует сложной агрегации.\n"
        "3. Не выдумывай цифры и структуру данных. Опирайся строго на схему графа:\n"
        f"{json.dumps(entities_summary, ensure_ascii=False)}"
    )
    
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]

    # Main reflection loop allowing the LLM to make multiple consecutive tool calls
    for _ in range(4):
        # Retry mechanism for API rate limiting
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
                    print(f"  [debug] API limit. Ожидание {wait} сек...")
                    time.sleep(wait)
                else:
                    raise
        else:
            return "ОШИБКА: Превышен лимит попыток дозвониться до API."

        message = response.choices[0].message

        # If no tools are called, return the final textual response
        if not message.tool_calls:
            return message.content

        messages.append(message)

        for call in message.tool_calls:
            args = json.loads(call.function.arguments)
            print(f"  [debug] Вызван инструмент: {call.function.name}, параметры: {args}")
            
            try:
                if call.function.name == "write_new_tool":
                    result = handle_write_new_tool(schema, question, **args)
                else:
                    result = execute_registry_entry(schema, data, call.function.name, args)
                
                content = json.dumps(result, ensure_ascii=False, default=str)
                print(f"  [debug] Результат: {content[:200]}...")
                
            except Exception as exc: 
                content = f"ОШИБКА: {exc}"
                print(f"  [debug] {content}")

            messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.function.name,
                "content": content,
            })

    return "ОШИБКА: Превышен лимит циклов рефлексии."


if __name__ == "__main__":
    print("=" * 60)
    print("Semantic Router (Single Role - Telemetry Only)")
    print("=" * 60)
    
    while True:
        try:
            q = input("\nПользователь: ").strip()
            if q.lower() in ("exit", "quit", "выход"):
                break
            if not q:
                continue
                
            start_time = time.time()
            answer = ask(q)
            elapsed = time.time() - start_time
            
            print(f"\nМета-Агент: {answer}")
            print(f"[Время отклика: {elapsed:.2f} сек]")
            print("-" * 60)
            
        except KeyboardInterrupt:
            print("\nЗавершение работы...")
            break
