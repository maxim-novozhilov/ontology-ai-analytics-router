# Ontological AI Router

An architectural concept and working prototype of an intelligent platform designed for analyzing dirty operational data.

The project addresses the core issue of LLMs in the Enterprise domain — numeric hallucinations. Instead of providing an LLM with direct access to raw tables or relying on on-the-fly SQL generation, the router establishes a rigid semantic bridge (an ontology) between the user and the underlying data layer. The model operates as an intelligent dispatcher, while all data processing is executed via strictly deterministic code.

---

## 🧠 Core Concept: Three-Tier Architecture

The system is split into three isolated layers, ensuring 100% mathematical accuracy in response formulation:

### Level 1: Deterministic Foundation (Data & Logic)

The raw data and processing layer. This prototype utilizes a synthetic JSON payload simulating a complex infrastructure environment complete with missing values, data glitches, and accounting source discrepancies. It also includes a placeholder for a VRP route solver. Core principle: dirty data is never purged; instead, it receives routing allowance flags (`data_flags`) processed by downstream logic.

### Level 2: Semantic Graph (Ontology)

The `ontology_schema.json` file serves as the system's structural map. The graph stores no raw data; it defines business entities (Tower Site, Genset, Audit Report), their relations, and access specifications (`tools_registry`) used by the interpreter to fetch metrics. The LLM views only this schema, eliminating hallucinated key names or fields.

### Level 3: Agentic Environment & Self-Extension (AI Core)

The operational AI orchestration layer (`semantic_router.py` + `interpreter.py`).

* **Data Firewall:** The router maps natural language queries to explicit tool declarations in the ontology graph. The universal interpreter executes deterministic Python logic and returns concise summaries, preserving context window capacity.

* **Meta-Agent (Self-Extension):** When presented with non-standard queries lacking pre-built declarations, the LLM leverages the ontology schema to generate new Python scripts dynamically, write them to disk, register them in the graph, and execute them on the fly.

---

## 🚀 Proven Capability (Prototype Testing)

* **Zero Calculation Hallucinations:** Delegating numeric aggregations (`count`, `filter`, `lookup`) to a deterministic interpreter eliminates arithmetic mistakes by the LLM.

* **Effective Self-Extension:** The meta-agent reliably authors custom tools during runtime (e.g., compiling summary dashboards from `audit.summary_report` or identifying fuel consumption anomalies) using `write_new_tool`.

* **Ontology Blindness as a Security Feature:** If requested entities or fields are absent from the graph schema, the system returns an explicit failure or zero count rather than fabricating plausible but false figures.

---

## 🛠 Architectural Lessons Learned

1. **Exact Schema Alignment:** The ontology graph must be a 1:1 mirror of the underlying data payload. Any discrepancy in nesting levels or key names causes dynamic scripts to fail.

2. **Strict Output Prompts:** Even with verified execution outputs, an LLM may attempt to paraphrase numerical results. System prompts must enforce strict constraints, such as *"state verbatim, do not recompute"*.

---

## 📂 Repository Structure

```text
docs/
  structure.txt              # Complete Level 1 data structure template
ontology/
  ontology_schema.json       # Level 2 semantic graph (entities & tools_registry)
prototype/
  interpreter.py             # Universal deterministic execution engine
  semantic_router.py         # AI router with self-extension capability (Mistral API)
  data/telemetry.json        # Synthetic demo dataset
data/
  generate_synthetic_data.py # Synthetic data generator for stress tests
```
---

## ⚙️ Running the Prototype

Requires a free API key from Mistral API (`console.mistral.ai`)[cite: 15].

```bash
cd prototype
pip install mistralai
python3 interpreter.py                             # Local graph/interpreter execution check
MISTRAL_API_KEY="..." python3 semantic_router.py   # Run the AI router agent
```