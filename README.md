# Ontological AI Router

This repository is a public, synthetic-data prototype of an ontology-backed AI analytics router for telecom tower operations. It demonstrates how an LLM can select tools from a business schema while deterministic Python performs the calculations.

The dataset is deliberately synthetic and contains no production identifiers or telemetry. The original architecture remains the point of the project: isolate messy operational data, describe it with an ontology, and keep numeric execution outside the language model.

## Architecture

### Level 1: deterministic data and execution

`data/synthetic_telemetry.json` contains 100 generated tower records plus audit, accounting, regional, and historical analytics blocks. `interpreter.py` executes declarative `lookup`, `filter`, `count`, and `get_all` tools. Its data firewall exports lists larger than 15 records to `exports/` instead of returning them directly to the model.

### Level 2: semantic graph

`ontology_schema.json` defines the entities, relationships, fields, allowed values, and tool registry. It contains the access contract, not a second copy of the data. Keeping the schema aligned with the JSON payload is essential: the interpreter resolves real payload paths such as `telemetry[]` and `audit.regional_report`.

### Level 3: semantic router and self-extension

`semantic_router.py` converts the registry into Mistral function definitions and routes natural-language questions to the interpreter. When the registered tools cannot express a complex aggregation, the model may call `write_new_tool`. The generated Python file is saved under `tools/`, registered for the current run, executed, and appended to `suggested_tools.json` for later validation.

This is a quarantine workflow, not a security sandbox. Generated code is executed in the local Python process, so the prototype must not be exposed to untrusted prompts or production data. A real sandbox is still a planned capability.

## Validation

[validation.md](validation.md) is the validation artifact for the prototype. It contains ten English versions of business questions from the initial Russian list, their selected registry tools, parameters, and results produced from the synthetic snapshot.

The report uses the deterministic registry/interpreter path. Running the Mistral conversation loop additionally requires an API key; the generated-tool path is implemented, but this repository does not claim sandbox isolation or API-backed execution for every example.

## Repository structure

```text
data/
  generate_synthetic_data.py       # Reproducible generator (seed 42)
  synthetic_telemetry.json         # Public synthetic snapshot
docs/
  structure.txt                    # Data structure and Level 1 contract
validation.md                      # Ten tested business questions and outputs
ontology_schema.json               # Entities, relationships, and tool registry
interpreter.py                     # Deterministic declaration interpreter
semantic_router.py                 # Mistral router and self-extension flow
exports/                           # Runtime data-firewall exports
tools/                             # Runtime-generated tools
suggested_tools.json               # Runtime tool-validation log
```

## Run locally

```bash
python3 -m pip install mistralai
python3 data/generate_synthetic_data.py
python3 interpreter.py
python3 -m unittest discover -s tests
MISTRAL_API_KEY="..." python3 semantic_router.py
```

The generator, interpreter, and tests are local and deterministic. The last command starts the interactive semantic router and uses the Mistral API.
