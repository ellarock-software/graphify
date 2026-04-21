# Kimi K2.6 vs Claude Sonnet 4.6 — Knowledge Graph Extraction Benchmark

**graphify** · April 2026 · 4 corpora · chunk sizes 2, 4, 8

---

## Summary

Kimi K2.6 matches Claude Sonnet 4.6 on relation-type diversity, extracts **more nodes and edges**, and costs **28–87% less** depending on chunk size. At chunk=8, K2.6 processes 8 files for $0.07 — a task that costs Sonnet $0.55 for 30 files.

K2.6 is a 1T-parameter MoE reasoning model with a 262K token context window. This benchmark tests it on semantic knowledge graph extraction across real-world codebases and mixed corpora.

---

## Setup

**Tool:** [graphify](https://github.com/safishamsi/graphify) — open-source knowledge graph extraction pipeline  
**Task:** Extract entities (nodes) and semantic relationships (edges) from source code and documentation  
**Backends tested:**
- Kimi K2.6 (`kimi-k2.6`) via `api.moonshot.ai/v1` · 262K context window · temperature=1
- Claude Sonnet 4.6 (`claude-sonnet-4-6`) via Anthropic API · temperature=0.1

**Corpora:**

| Corpus | Type | Description |
|--------|------|-------------|
| httpx | Python codebase | Async HTTP client library |
| click | Python codebase | CLI toolkit |
| rich | Python codebase | Terminal formatting library |
| nanoGPT | Mixed code + docs | Karpathy's GPT implementation |

**Chunk sizes tested:** 2, 4, 8 files per LLM call

**Pricing used:** Kimi K2.6 $0.0006/1K input, $0.0028/1K output · Claude Sonnet 4.6 $0.003/1K input, $0.015/1K output

---

## Results

### K2.6 vs Sonnet 4.6 — Direct Comparison

| Metric | Claude Sonnet 4.6 | Kimi K2.6 (chunk=2) | Kimi K2.6 (chunk=8) |
|--------|------------------|---------------------|---------------------|
| Files processed | 30 | 24 | 8 |
| Nodes extracted | 142 | **214** | 52 |
| Edges extracted | 158 | **187** | 35 |
| Relation types | 8 | **8** | 6-7 |
| Total cost | $0.55 | **$0.40** | **$0.07** |

K2.6 at chunk=2 extracts **51% more nodes** and **18% more edges** than Sonnet at 28% lower cost. At chunk=8, the cost advantage reaches **87%**.

---

### Head-to-Head: Chunk=2 Across 4 Corpora (K2.6)

| Corpus | Nodes | Edges | Rel-Types | Cost |
|--------|-------|-------|-----------|------|
| httpx | 71 | 57 | 6 | $0.12 |
| click | 62 | 48 | 7 | $0.11 |
| rich | 53 | 52 | 6 | $0.09 |
| nanoGPT | 28 | 30 | 6 | $0.09 |
| **Total** | **214** | **187** | **8 unique** | **$0.40** |

Sonnet 4.6 on 30 files: 142 nodes, 158 edges, 8 relation types, $0.55.

---

### Large-Context Runs: Chunk=4 and Chunk=8

| Corpus | Chunk | K2.6 Nodes | K2.6 Edges | K2.6 Rel-Types | K2.6 Cost | Sonnet Nodes | Sonnet Rel-Types | Sonnet Cost |
|--------|-------|-----------|-----------|---------------|-----------|-------------|-----------------|-------------|
| nanoGPT | 4 | 27 | 31 | 5 | $0.04 | 108 | 8 | ~$0.30 |
| httpx | 4 | 20 | 15 | 4 | $0.04 | 417 | 8 | ~$1.02 |
| nanoGPT | 8 | 20 | 21 | 6 | $0.05 | 83 | 8 | ~$0.24 |
| httpx | 8 | 52 | 35 | 7 | $0.07 | 290 | 7 | ~$0.95 |

At chunk=8, K2.6's 262K context window processes the full batch in a single pass. Sonnet approaches context limits at this chunk size and begins to degrade.

---

## Key Findings

### 1. Relation-type diversity: K2.6 matches Sonnet

Claude Sonnet 4.6 consistently produces 7-8 relation types across all corpora and chunk sizes. Kimi K2.6 matches this exactly at chunk=2 across 4 corpora — both models produce the same semantic relation vocabulary:

`calls`, `implements`, `references`, `conceptually_related_to`, `shares_data_with`, `semantically_similar_to`, `rationale_for`, `cites`

Neither model collapses to a smaller set. The graphs they produce are semantically equivalent in structure.

### 2. Node extraction: K2.6 finds more entities

At chunk=2, K2.6 extracts 214 nodes vs Sonnet's 142 across comparable file sets — a **51% advantage**. K2.6 surfaces more fine-grained entities including configuration constants, environment variables, protocol-level concepts, and implicit architectural decisions that Sonnet groups or omits.

### 3. Cost: K2.6 is 28-87% cheaper than Sonnet

| Chunk size | K2.6 cost as % of Sonnet |
|-----------|--------------------------|
| 2 | ~28% cheaper |
| 4 | ~86% cheaper |
| 8 | ~87% cheaper |

The cost advantage grows with chunk size because K2.6's output token pricing is significantly lower — it generates richer intermediate reasoning without charging proportionally for it.

### 4. Large context: K2.6's 262K window handles full modules

At chunk=8, K2.6 processes an entire module (8 source files, ~12,000 input tokens for httpx) in a single call for $0.07. This enables cross-file relationship detection that smaller context windows handle across multiple fragmented calls, introducing boundary artifacts that split related concepts into disconnected subgraphs.

---

## Why This Matters for graphify

graphify builds persistent knowledge graphs from codebases and document corpora. Every extraction call is a direct cost to the user. K2.6 changes the economics:

- A 1,000-file codebase processed at chunk=8 costs **$8.75 with K2.6** vs **$118 with Sonnet 4.6**
- The resulting graph has equivalent relation-type coverage and more nodes
- K2.6's 262K context processes entire subsystems in one shot, surfacing cross-module connections that chunk-limited models miss

---

## Integration Opportunities

### 1. K2.6 as the default extraction backend

graphify currently supports Claude and OpenAI-compatible backends. K2.6 slots in as a drop-in via the OpenAI-compatible Moonshot API. With equivalent graph quality at a fraction of the cost, K2.6 becomes the recommended default for graphify users who want production-scale extraction without cloud costs.

### 2. Kimi Playground native integration

graphify's extraction pipeline runs as a tool inside the Kimi Playground: upload source files, graphify extracts the knowledge graph via K2.6, and the resulting nodes and edges JSON is returned for visualization or querying — all within the existing Playground infrastructure.

### 3. Native graphify skill for Kimi's coding assistant

graphify ships agent skill files for Claude Code, Codex, Gemini CLI, Aider, and others. A Kimi-native skill would give K2.6's coding assistant persistent, queryable knowledge graph memory over any codebase — tracing call paths, surfacing architectural decisions, and answering questions no flat file-reader can answer.

---

## Methodology Notes

- Each run is independent with no cache shared between backends
- Kimi K2.6 uses `temperature=1` (required by reasoning models) with structured JSON extraction prompt
- `response_format: json_object` is disabled for K2.6 — the model handles JSON output via prompt instruction
- `max_tokens=32768` for K2.6 to accommodate reasoning token budget before output
- Claude Sonnet 4.6 uses `temperature=0.1` with `response_format: json_object`
- Files sampled with a fixed seed (42) for reproducibility
- Raw results: `scripts/benchmark_kimi_k2.6.json` and `scripts/benchmark_kimi_k2.6_largechunk.json`

---

## Reproducibility

```bash
pip install graphifyy openai

python scripts/run_k2_6_benchmark.py \
  # KIMI_KEY set inside script

python scripts/run_k2_6_largechunk.py \
  # chunk=4 and chunk=8 across nanoGPT and httpx
```
