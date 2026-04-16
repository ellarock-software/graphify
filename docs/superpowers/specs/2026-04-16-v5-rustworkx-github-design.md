# graphify v5: rustworkx backend + GitHub repo ingestion

**Date:** 2026-04-16  
**Branch:** v5  
**Status:** Approved

---

## Summary

v5 introduces two major changes on a new branch:

1. **GitHub repo ingestion** -- users can pass a GitHub URL directly instead of a local path. graphify clones the repo and runs the full pipeline on it.
2. **rustworkx graph backend** -- NetworkX replaced with rustworkx throughout, with a NetworkX fallback if rustworkx is not installed. Adds `--dag` flag for acyclic directed graphs and parallel shortest-path in `graphify path`.

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
- Subsequent runs: `git -C <dest> pull --ff-only`
- Returns the local path on success

### Integration point

`__main__.py`: single call to `resolve_target()` before the path is passed to `detect()` and `extract()`. No other changes to `__main__.py`.

### Error handling

| Condition | Behaviour |
|-----------|-----------|
| Repo not found / private | Clear error message, exit 1 |
| git not installed | Error message pointing to git install, exit 1 |
| Network timeout | Retry once, then fail with message |
| Partial clone (disk full) | Detect incomplete state, clean up, report error |
| Already cloned, pull fails | Warn, use existing local copy |

---

## Feature 2: rustworkx graph backend

### Dependency

- `rustworkx` added as optional dependency: `pip install graphifyy[fast]`
- If not installed: fall back to NetworkX with a one-time warning
- `pyproject.toml`: `fast = ["rustworkx"]`, added to `all`

### Graph type mapping

| v4 (NetworkX) | v5 (rustworkx) |
|---------------|----------------|
| `nx.Graph` | `rustworkx.PyGraph` |
| `nx.DiGraph` | `rustworkx.PyDiGraph` |
| `nx.DiGraph` + `--dag` | `rustworkx.PyDAG` |

### ID mapping

rustworkx uses integer node indices internally. `build.py` maintains two dicts alongside every graph:
- `_id_to_idx: dict[str, int]` -- string node ID → rustworkx index
- `_idx_to_id: dict[int, str]` -- rustworkx index → string node ID

These are attached as `G._id_to_idx` and `G._idx_to_id` on the graph object so downstream modules can look up either direction without re-scanning.

### Module changes

**`build.py`**  
- `build_from_json()` returns a `PyGraph`/`PyDiGraph`/`PyDAG` (or `nx.Graph`/`nx.DiGraph` if rustworkx absent)
- ID normalization from v0.4.18 preserved
- Edge-add under `--dag`: cycle check via `rustworkx.is_directed_acyclic_graph()`; drop edge + warn on violation

**`cluster.py`**  
- Leiden (graspologic) unchanged -- takes adjacency matrix, not graph object
- Louvain fallback: replace `nx.community.louvain_communities()` with `rustworkx.community.louvain_communities()`
- Node list extraction uses `_idx_to_id` map

**`analyze.py`**  
- `betweenness_centrality`: replace `nx.betweenness_centrality()` with `rustworkx.betweenness_centrality()` (parallel)
- `edge_betweenness_centrality`: replace with `rustworkx.edge_betweenness_centrality()`
- `shortest_path`: replace `nx.shortest_path()` with `rustworkx.dijkstra_shortest_paths()` (parallel)
- All functions accept either graph type via duck-typed helper `_is_rustworkx(G)`

**`export.py`**  
- Replace `networkx.readwrite.json_graph.node_link_data()` with custom serializer that walks `G.node_indices()` and `G.edge_list()`
- SVG export (`nx.draw_networkx_*`): replaced with manual matplotlib scatter + line drawing using node positions from `rustworkx.spring_layout()`

**`serve.py`**  
- Replace `json_graph.node_link_data()` with same custom serializer as export.py
- MCP tool handlers updated to use `_id_to_idx` for node lookup

**`wiki.py`**  
- `nx.Graph` type hints replaced with union type
- Neighbour iteration uses `G.neighbors(idx)` + `_idx_to_id` lookup

### `--dag` flag

- New CLI flag: `graphify /path --dag`
- Uses `PyDAG` instead of `PyDiGraph`
- Cycle violations at edge-add time: drop edge, print warning to stderr
- Report includes topological sort order of god nodes
- skill.md updated to document `--dag`

### `graphify path` parallel shortest-path

- `analyze.py`: `shortest_path()` uses `rustworkx.dijkstra_shortest_paths()` with `parallel_threshold=500` (falls back to single-thread for small graphs)
- No CLI change -- transparent speedup

---

## Compatibility

### graph.json

Format unchanged. v5 reads v4 `graph.json` files without modification. The integer index mapping is rebuilt from the JSON node list on load.

### pip install

| Install | Graph backend | GitHub ingest |
|---------|--------------|---------------|
| `pip install graphifyy` | NetworkX (fallback) | yes |
| `pip install graphifyy[fast]` | rustworkx | yes |
| `pip install graphifyy[all]` | rustworkx | yes |

### Python version

Unchanged: Python 3.10+

---

## Testing

- All 433 existing tests must pass with both backends (NetworkX fallback + rustworkx)
- New tests:
  - `tests/test_github.py`: URL parsing, clone/update logic (mocked subprocess), error cases
  - `tests/test_build_rustworkx.py`: graph round-trip, ID mapping correctness, DAG cycle rejection
  - `tests/test_analyze_rustworkx.py`: betweenness output matches NetworkX within 1e-6 tolerance
  - `tests/test_cluster_rustworkx.py`: community structure matches within reasonable variance

---

## Files changed

| File | Change |
|------|--------|
| `graphify/github.py` | New |
| `graphify/build.py` | rustworkx backend, ID mapping |
| `graphify/cluster.py` | rustworkx Louvain fallback |
| `graphify/analyze.py` | parallel betweenness + shortest path |
| `graphify/export.py` | custom JSON serializer, matplotlib layout |
| `graphify/serve.py` | custom JSON serializer |
| `graphify/wiki.py` | graph type abstraction |
| `graphify/__main__.py` | `resolve_target()` call, `--dag` flag |
| `graphify/skill.md` | document `--dag`, GitHub URL input |
| `pyproject.toml` | `fast = ["rustworkx"]`, add to `all` |
| `tests/test_github.py` | New |
| `tests/test_build_rustworkx.py` | New |
| `tests/test_analyze_rustworkx.py` | New |
| `tests/test_cluster_rustworkx.py` | New |

---

## Out of scope for v5

- Private repo support (requires GitHub token -- future work)
- Incremental re-extraction after `git pull` (tracked via `--update`, already works once cloned)
- GraphQL / GitHub API (issues, PRs, file-level fetch) -- future work
- rustworkx GPU acceleration -- future work
