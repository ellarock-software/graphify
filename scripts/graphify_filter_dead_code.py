#!/usr/bin/env python3
"""
Filter graphify graph.json output to categorize nodes by:
1. Test functions (#[test] attribute) - marked with is_test_function: true
2. Test scope (#[cfg(test)] blocks) - marked with source_scope: "test"|"production"

This reduces false positives in dead-code audit reports by separating test code
from production code and excluding dynamically-invoked test functions.
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
import networkx as nx


def detect_test_function(source: str, label: str, source_location: str | int) -> bool:
    """
    Detect if a function has a #[test] attribute.

    Args:
        source: Full source file content
        label: Function name (e.g., "test_foo")
        source_location: Line number where function/attribute is (0-indexed or "L42")

    Returns:
        True if #[test] attribute is near the function definition
    """
    lines = source.split('\n')

    # Parse line number
    try:
        if isinstance(source_location, int):
            start_line = source_location
        else:
            start_line = int(source_location.lstrip('L')) if source_location.startswith('L') else int(source_location)
    except (ValueError, IndexError, AttributeError):
        return False

    # Find the actual function definition line (might be after attributes)
    fn_def_line = start_line
    while fn_def_line < len(lines) and f'fn {label}' not in lines[fn_def_line] and 'fn ' not in lines[fn_def_line]:
        fn_def_line += 1

    # Search backward from function definition for #[test]
    search_end = max(0, fn_def_line - 10)
    for i in range(fn_def_line - 1, search_end - 1, -1):
        if i >= 0 and i < len(lines):
            if '#[test]' in lines[i]:
                return True
            # Stop searching if we hit code that's not an attribute
            if lines[i].strip() and not lines[i].strip().startswith('#['):
                break

    return False


def find_cfg_test_blocks(source: str) -> List[Tuple[int, int]]:
    """
    Find all #[cfg(test)] block boundaries in source.

    Args:
        source: Full source file content

    Returns:
        List of (start_line, end_line) tuples for cfg(test) blocks
    """
    lines = source.split('\n')
    blocks = []
    block_start = None
    brace_depth = 0
    seen_opening_brace = False

    for i, line in enumerate(lines):
        # Check for #[cfg(test)] attribute
        if '#[cfg(test)]' in line or ('#[cfg(' in line and 'test' in line):
            block_start = i
            brace_depth = 0
            seen_opening_brace = False

        # Once we've seen the attribute, track braces
        if block_start is not None and block_start < i:
            if '{' in line:
                seen_opening_brace = True
                brace_depth += line.count('{')
            if seen_opening_brace:
                brace_depth -= line.count('}')

            # Block ends when we've seen the opening brace and now all braces are closed
            if seen_opening_brace and brace_depth == 0 and '}' in line:
                blocks.append((block_start, i + 1))
                block_start = None
                seen_opening_brace = False

    return blocks


def node_in_cfg_test_block(source_location: str, cfg_blocks: List[Tuple[int, int]]) -> bool:
    """
    Check if a node's line is within any #[cfg(test)] block.

    Args:
        source_location: Line number as "L42"
        cfg_blocks: List of (start_line, end_line) tuples

    Returns:
        True if node is inside a cfg(test) block
    """
    try:
        line_num = int(source_location.lstrip('L')) if source_location.startswith('L') else int(source_location)
    except (ValueError, IndexError):
        return False

    for start, end in cfg_blocks:
        if start <= line_num < end:
            return True

    return False


def filter_graph_json(graph: Dict[str, Any], source_root: str) -> Dict[str, Any]:
    """
    Filter graph.json by adding is_test_function and source_scope attributes.

    Args:
        graph: Loaded graph.json as dict
        source_root: Root directory for resolving source_file paths

    Returns:
        Modified graph with new attributes added to nodes
    """
    source_cache = {}

    for node in graph.get("nodes", []):
        source_file = node.get("source_file", "")
        if not source_file:
            node["source_scope"] = "unknown"
            continue

        # Try to resolve source file
        source_path = Path(source_file)
        if not source_path.exists():
            source_path = Path(source_root) / source_file
        if not source_path.exists():
            node["source_scope"] = "unknown"
            continue

        # Load source file (with caching)
        if source_file not in source_cache:
            try:
                source_cache[source_file] = source_path.read_text()
            except Exception:
                node["source_scope"] = "unknown"
                continue

        source = source_cache[source_file]
        label = node.get("label", "")
        source_location = node.get("source_location", "")

        # Check for #[test] attribute
        if label and detect_test_function(source, label, source_location):
            node["is_test_function"] = True

        # Find cfg(test) blocks
        cfg_blocks = find_cfg_test_blocks(source)

        # Determine scope
        if node_in_cfg_test_block(source_location, cfg_blocks):
            node["source_scope"] = "test"
        else:
            node["source_scope"] = "production"

    return graph


def get_isolated_nodes_by_scope(G: nx.Graph) -> Dict[str, List[str]]:
    """
    Identify isolated nodes (degree == 0) separated by source_scope.

    Args:
        G: NetworkX graph with nodes having source_scope attribute

    Returns:
        Dict with keys "production" and "test", each containing list of node ids
    """
    result = {"production": [], "test": []}

    for node_id in G.nodes():
        if G.degree(node_id) == 0:
            scope = G.nodes[node_id].get("source_scope", "unknown")
            if scope in result:
                result[scope].append(node_id)

    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: graphify_filter_dead_code.py <graphify-out/graph.json> [source-root]")
        sys.exit(1)

    graph_path = Path(sys.argv[1])
    source_root = sys.argv[2] if len(sys.argv) > 2 else str(graph_path.parent.parent)

    # Load graph
    graph = json.loads(graph_path.read_text())

    # Filter
    filtered = filter_graph_json(graph, source_root)

    # Save filtered graph
    output_graph = graph_path.parent / "graph-filtered.json"
    output_graph.write_text(json.dumps(filtered, indent=2))
    print(f"Saved filtered graph to {output_graph}")

    # Convert to NetworkX and identify isolated nodes
    G = nx.Graph()
    for node in filtered.get("nodes", []):
        node_id = node.get("id")
        if node_id:
            G.add_node(node_id, **node)
    for link in filtered.get("links", []):
        source = link.get("_src") or link.get("source")
        target = link.get("_tgt") or link.get("target")
        if source and target:
            G.add_edge(source, target)

    # Count isolated nodes by scope
    isolated_by_scope = get_isolated_nodes_by_scope(G)

    # Count all nodes by scope
    all_by_scope = {}
    for node_id in G.nodes():
        scope = G.nodes[node_id].get("source_scope", "unknown")
        all_by_scope[scope] = all_by_scope.get(scope, 0) + 1

    # Count test functions
    test_functions = sum(1 for n in G.nodes() if G.nodes[n].get("is_test_function"))

    # Print summary
    print("\n=== Isolated Node Summary ===")
    print(f"Production code nodes: {all_by_scope.get('production', 0)}")
    print(f"  - Isolated: {len(isolated_by_scope.get('production', []))}")
    print(f"Test code nodes: {all_by_scope.get('test', 0)}")
    print(f"  - Isolated: {len(isolated_by_scope.get('test', []))}")
    print(f"Test functions marked: {test_functions}")
    print(f"\nFiltered graph: {len(filtered['nodes'])} nodes, {len(filtered['links'])} edges")
