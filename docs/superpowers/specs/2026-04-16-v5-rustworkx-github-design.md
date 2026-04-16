# graphify v5: rustworkx backend + GitHub repo ingestion

**Date:** 2026-04-16  
**Branch:** v5  
**Status:** Approved (revised after senior engineering review)

---

## Summary

v5 introduces two major changes on a new branch:

1. **GitHub repo ingestion** -- users can pass a GitHub URL directly instead of a local path. graphify clones the repo and runs the full pipeline on it.
2. **rustworkx graph backend** -- rustworkx replaces NetworkX as the in-memory graph type throughout, with a NetworkX fallback if rustworkx is not installed. Adds `--dag` flag for acyclic directed graphs and parallel betweenness/shortest-path.

Both changes are independent. The user-facing API and `graph.json` format are unchanged.

---

## Feature 1: GitHub repo ingestion

### New file: `graphify/github.py`

**`resolve_target(input: str) -> Path`**  
Called by `__main__.py` before extraction. If input looks like a GitHub URL, delegates to `clone_or_update()` and returns the local clone path. Otherwise returns `Path(input)` unchanged.

Recognised URL formats:
- `https://github.com/org/repo`
- `http://github.com/org/repo`
- `github.com/org/repo`
- `org/repo` (shorthand, only if it contains exactly one `/` and no dots)

**`clone_or_update(org: str, repo: str, base_dir: Path) -> Path`**  
- Clone destination: `~/.graphify/repos/org/repo/`
- First run: `git clone --depth 1 https://github.com/org/repo <dest>`
- Subsequent runs (dest already exists):
  ```
  git -C <dest> fetch --depth 1 origin
  git -C <dest> reset --hard origin/HEAD
  ```
  This unconditionally updates to the remote tip without requiring fast-forward eligibility and keeps history shallow. `git pull --ff-only` is explicitly avoided -- it fails on shallow clones when the upstream has rebased or advanced more than one commit.
- Returns the local path on success

### Integration point

`__main__.py`: single call to `resolve_target()` before the path is passed to `detect()` and `extract()`. No other changes to `__main__.py`.

### Error handling

| Condition | Behaviour |
|-----------|-----------|
| Repo not found / private | Clear error message, exit 1 |
| git not installed | `"git is required for GitHub repo ingestion. Install git and retry."`, exit 1 |
| Network timeout | Retry once, then fail with message |
| Partial clone (disk full, `.git` exists but incomplete) | Delete dest dir, report error, exit 1 |
| Already cloned, fetch/reset fails | Warn, continue with existing local copy |

---

## Feature 2: rustworkx graph backend

### Dependency

- `rustworkx` added as optional dependency: `pip install graphifyy[fast]`
- If not installed: fall back to NetworkX with a one-time warning printed to stderr:
  `"[graphify] rustworkx not installed -- using NetworkX. Install graphifyy[fast] for 2-10x speedup."`
- `pyproject.toml`: `fast = ["rustworkx"]`, added to `all`
- Note: NetworkX remains a hard dependency (required for Louvain community detection fallback -- rustworkx has no built-in community detection)

### Graph type mapping

| v4 (NetworkX) | v5 rustworkx backend | v5 NetworkX fallback |
|---------------|----------------------|----------------------|
| `nx.Graph` | `rustworkx.PyGraph` | `nx.Graph` |
| `nx.DiGraph` | `rustworkx.PyDiGraph` | `nx.DiGraph` |
| `nx.DiGraph` + `--dag` | `rustworkx.PyDAG(check_cycle=True)` | `nx.DiGraph` (no cycle enforcement) |

### GraphBundle -- the central abstraction

`PyGraph`/`PyDiGraph`/`PyDAG` are Rust extension types (pyo3 `#[pyclass]`) with no `__dict__` slot. Attribute assignment (`G._id_to_idx = ...`) raises `AttributeError`. The correct design is a thin dataclass returned by `build_from_json()` and passed through the entire pipeline:

```python
# graphify/utils.py  (new file)
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Union
import networkx as nx

try:
    import rustworkx as rx
    _RX_GRAPH_TYPES = (rx.PyGraph, rx.PyDiGraph, rx.PyDAG)
    HAS_RUSTWORKX = True
except ImportError:
    _RX_GRAPH_TYPES = ()
    HAS_RUSTWORKX = False

AnyGraph = Union["rx.PyGraph", "rx.PyDiGraph", "rx.PyDAG", nx.Graph, nx.DiGraph]

@dataclass
class GraphBundle:
    graph: AnyGraph
    id_to_idx: dict[str, int] = field(default_factory=dict)   # empty for NetworkX backend
    idx_to_id: dict[int, str] = field(default_factory=dict)   # empty for NetworkX backend

def is_rustworkx(bundle: GraphBundle) -> bool:
    return isinstance(bundle.graph, _RX_GRAPH_TYPES)
```

Every function that currently accepts `nx.Graph` is updated to accept `GraphBundle`. The internal graph and lookup dicts are accessed via `bundle.graph`, `bundle.id_to_idx`, `bundle.idx_to_id`.

`is_rustworkx()` lives in `graphify/utils.py`. It is imported by every module that needs to branch on backend. No copies.

### ID mapping

rustworkx uses integer node indices internally. `GraphBundle` carries two dicts:
- `id_to_idx: dict[str, int]` -- string node ID → rustworkx index
- `idx_to_id: dict[int, str]` -- rustworkx index → string node ID

These are populated in `build_from_json()` as nodes are added and carried through the pipeline in the `GraphBundle`. The NetworkX fallback leaves both dicts empty (not needed).

### API translation reference

The following access patterns appear ~35 times across `analyze.py`, `cluster.py`, `export.py`, `serve.py`, `wiki.py`. Each must be dual-pathed via `is_rustworkx()`:

| NetworkX | rustworkx equivalent |
|----------|---------------------|
| `G.nodes[nid]` | `G[id_to_idx[nid]]` |
| `G.nodes(data=True)` | `zip(G.node_indices(), G.nodes())` → use `idx_to_id[idx]` for ID |
| `G.edges(nid, data=True)` | `[(idx_to_id[u], idx_to_id[v], G.get_edge_data(u,v)) for u,v in G.incident_edges(id_to_idx[nid])]` |
| `G.degree(nid)` | `G.degree(id_to_idx[nid])` |
| `G.neighbors(nid)` → string IDs | `[idx_to_id[i] for i in G.neighbors(id_to_idx[nid])]` |
| `G.edges[u, v]` | `G.get_edge_data(id_to_idx[u], id_to_idx[v])` |
| `G.number_of_nodes()` | `G.num_nodes()` |
| `G.number_of_edges()` | `G.num_edges()` |

### Module changes

**`graphify/utils.py`** (new)
- `GraphBundle` dataclass
- `is_rustworkx(bundle)` helper
- `AnyGraph` type alias

**`graphify/build.py`**
- `build_from_json()` returns `GraphBundle` (not a bare graph)
- Nodes added via `G.add_node(payload_dict)` → captures returned index → populates `id_to_idx`/`idx_to_id`
- Edges: `src_idx = id_to_idx.get(src)`, `tgt_idx = id_to_idx.get(tgt)` -- missing indices skip the edge (same semantics as v4 node_set check)
- ID normalization from v0.4.18 preserved (normalize before lookup)
- `--dag` edge-add: wrap in `try/except rustworkx.DAGWouldBeCyclic` -- drop edge, print warning to stderr. Do NOT use `rustworkx.is_directed_acyclic_graph()` for pre-checking (it cannot pre-check a prospective edge)
- NetworkX fallback: `GraphBundle(graph=nx.Graph(), id_to_idx={}, idx_to_id={})`

**`graphify/cluster.py`**
- `_partition(bundle)` replaces `_partition(G)`
- Leiden (graspologic): graspologic's `leiden()` accepts a NetworkX graph. When rustworkx backend is active, convert to NetworkX for leiden only:
  ```python
  if is_rustworkx(bundle):
      G_nx = nx.Graph()
      for u, v in bundle.graph.edge_list():
          G_nx.add_edge(bundle.idx_to_id[u], bundle.idx_to_id[v])
      communities = leiden(G_nx)
  else:
      communities = leiden(bundle.graph)
  ```
- Louvain fallback: stays `nx.community.louvain_communities()` -- rustworkx has no built-in community detection. When rustworkx backend is active, same edge-list conversion as above.
- Node list extraction from leiden/louvain results uses `idx_to_id` where needed

**`graphify/analyze.py`**
- All public functions updated to accept `GraphBundle`
- `betweenness_centrality`: `rustworkx.betweenness_centrality(bundle.graph)` returns `dict[int, float]` -- remap to string IDs via `idx_to_id`
- `edge_betweenness_centrality`: `rustworkx.edge_betweenness_centrality(bundle.graph)` returns `dict[(int,int), float]` -- remap edge tuples to string ID pairs
- `shortest_path`: `rustworkx.dijkstra_shortest_paths(bundle.graph, src_idx)` returns `dict[int, list[int]]` -- decode path using `idx_to_id` at every position
- `suggest_questions()`: calls `nx.betweenness_centrality(G, k=k)` with approximation parameter `k`. rustworkx's `betweenness_centrality()` has no `k` parameter (always exact, parallel). When rustworkx backend active, drop `k` and call `rustworkx.betweenness_centrality(bundle.graph)`. This is always exact but faster due to parallelism; behavior change is documented.
- `_is_rustworkx()` removed -- use `is_rustworkx()` from `utils.py`

**`graphify/export.py`**
- Replace `json_graph.node_link_data()` with `_bundle_to_json(bundle)` -- custom serializer that produces the same schema as `node_link_data()` (see JSON schema below)
- SVG: `rustworkx.spring_layout(bundle.graph)` returns `dict[int, list[float]]` (integer-keyed). Map to string IDs via `idx_to_id` before passing to matplotlib. Node drawing iterates `zip(bundle.graph.node_indices(), bundle.graph.nodes())`.

**`graphify/serve.py`**
- `_load_graph()` uses same custom deserializer as export.py (loads `graph.json` → `GraphBundle`)
- MCP tool handlers updated: node lookups via `bundle.id_to_idx[node_id]`, neighbour traversal via API translation table above

**`graphify/wiki.py`**
- Accepts `GraphBundle`, uses `is_rustworkx()` + API translation table for all graph traversal

### JSON serializer schema

The custom serializer `_bundle_to_json(bundle)` must produce output byte-compatible with `networkx.readwrite.json_graph.node_link_data()` so v4 `graph.json` files load without modification in v5. The schema:

```json
{
  "directed": true,
  "multigraph": false,
  "graph": {},
  "nodes": [
    {"id": "session_validatetoken", "label": "ValidateToken", "file_type": "code", ...}
  ],
  "links": [
    {"source": "session_validatetoken", "target": "other_node",
     "relation": "calls", "confidence": "EXTRACTED", "weight": 1.0, ...}
  ]
}
```

Key points:
- Top-level key is `"links"` not `"edges"` (this is what `node_link_data()` produces; `build.py` already handles both via the `"links"` → `"edges"` remap on load)
- Node dicts include all attributes from `bundle.graph.nodes()` plus `"id"` key
- Edge dicts include all attributes from `bundle.graph.get_edge_data()` plus `"source"` and `"target"` string IDs

### `--dag` flag

- New CLI flag: `graphify /path --dag`
- `build_from_json()` receives `dag=True`, uses `rustworkx.PyDAG(check_cycle=True)`
- Cycle violations: `except rustworkx.DAGWouldBeCyclic` → drop edge, print `"[graphify] warning: skipping edge {src} → {tgt} (would create cycle)"` to stderr
- Report includes topological sort order of god nodes via `rustworkx.topological_sort(bundle.graph)` decoded with `idx_to_id`
- NetworkX fallback when rustworkx absent: `--dag` flag accepted but cycle enforcement is silently skipped (no PyDAG available); warning printed once
- `"dag": true` written to `graph.json` metadata so serve.py can surface it in `get_graph_info` MCP tool. DAG enforcement is build-time only -- reloaded graphs are not re-enforced.
- `skill.md` updated to document `--dag`

### `graphify path` shortest-path speedup

- `analyze.py`: `shortest_path()` uses `rustworkx.dijkstra_shortest_paths(bundle.graph, src_idx)` -- no `parallel_threshold` parameter (rustworkx Dijkstra is always Rust-backed; per-query overhead reduction vs NetworkX is already ~10x)
- Path result decoded via `idx_to_id` at every element
- No CLI change -- transparent speedup

---

## Compatibility

### graph.json

Format unchanged -- the custom serializer produces identical output to `node_link_data()`. v5 reads v4 `graph.json` files without modification. The integer index mapping is rebuilt from the JSON node list on load.

### pip install

| Install | Graph backend | GitHub ingest |
|---------|--------------|---------------|
| `pip install graphifyy` | NetworkX (fallback) | yes |
| `pip install graphifyy[fast]` | rustworkx | yes |
| `pip install graphifyy[all]` | rustworkx | yes |

NetworkX remains a hard dependency in all cases (required for community detection).

### Python version

Unchanged: Python 3.10+

---

## Testing

- All 433 existing tests must pass on the NetworkX fallback path (rustworkx not installed)
- Dual-backend coverage: `conftest.py` adds a `graph_backend` pytest fixture parametrized over `["networkx", "rustworkx"]`. Tests that create graphs import the fixture and get a `GraphBundle` built with the appropriate backend. This gives dual-backend coverage without duplicating test files.
- New tests:
  - `tests/test_github.py`: URL parsing (all four formats), clone logic (mocked `subprocess.run`), update logic (mocked fetch+reset), each error case
  - `tests/test_build_rustworkx.py`: `GraphBundle` round-trip, `id_to_idx`/`idx_to_id` correctness, DAG cycle rejection (`DAGWouldBeCyclic` caught), JSON serializer output matches `node_link_data()` byte-for-byte on a fixture graph
  - `tests/test_analyze_rustworkx.py`: betweenness output matches NetworkX within 1e-6 tolerance; `suggest_questions()` betweenness behavior change documented in test comment
  - `tests/test_cluster_rustworkx.py`: leiden edge-list conversion produces same community structure as direct NetworkX call on same graph

---

## Files changed

| File | Change |
|------|--------|
| `graphify/github.py` | New -- GitHub URL resolution + clone/update |
| `graphify/utils.py` | New -- `GraphBundle`, `is_rustworkx()`, `AnyGraph` |
| `graphify/build.py` | Returns `GraphBundle`; rustworkx + NetworkX dual backend |
| `graphify/cluster.py` | `GraphBundle` input; leiden edge-list conversion |
| `graphify/analyze.py` | `GraphBundle` input; rustworkx parallel betweenness + path |
| `graphify/export.py` | `GraphBundle` input; custom JSON serializer; matplotlib layout fix |
| `graphify/serve.py` | `GraphBundle` input; custom deserializer; MCP handler updates |
| `graphify/wiki.py` | `GraphBundle` input; dual-path graph traversal |
| `graphify/__main__.py` | `resolve_target()` call; `--dag` flag |
| `graphify/skill.md` | Document `--dag`; GitHub URL input |
| `pyproject.toml` | `fast = ["rustworkx"]`; add to `all` |
| `tests/conftest.py` | `graph_backend` fixture parametrized over both backends |
| `tests/test_github.py` | New |
| `tests/test_build_rustworkx.py` | New |
| `tests/test_analyze_rustworkx.py` | New |
| `tests/test_cluster_rustworkx.py` | New |

---

## Out of scope for v5

- Private repo support (requires GitHub token -- future work)
- Incremental re-extraction after `git pull` (`--update` already handles this once cloned)
- GraphQL / GitHub API (issues, PRs, file-level fetch) -- future work
- rustworkx GPU acceleration -- future work
- DAG cycle enforcement on graph reload (enforcement is build-time only)
