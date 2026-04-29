"""Tests for filter_dead_code.py - filtering #[test] functions and #[cfg(test)] blocks."""
import json
import tempfile
from pathlib import Path
import sys

# Import the filter module (will fail if it doesn't exist yet)
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.graphify_filter_dead_code import (
    detect_test_function,
    find_cfg_test_blocks,
    node_in_cfg_test_block,
    filter_graph_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


# Helper to create a minimal graph.json
def make_test_graph(nodes, links=None):
    """Create a minimal graph.json structure."""
    return {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": nodes,
        "links": links or [],
    }


class TestDetectTestFunction:
    """Test detection of #[test] attribute on functions."""

    def test_simple_test_function(self):
        """Simple #[test] fn should be detected."""
        source = """
#[test]
fn test_foo() {
    assert!(true);
}
"""
        result = detect_test_function(source, "test_foo", 2)
        assert result is True, "Failed to detect #[test] function"

    def test_non_test_function(self):
        """Regular function should not be marked as test."""
        source = """
fn regular_foo() {
    println!("hello");
}
"""
        result = detect_test_function(source, "regular_foo", 1)
        assert result is False, "Incorrectly marked regular function as test"

    def test_test_with_attributes(self):
        """#[test] with additional attributes should be detected."""
        source = """
#[test]
#[ignore]
fn test_ignored() {
    assert!(false);
}
"""
        result = detect_test_function(source, "test_ignored", 2)
        assert result is True, "Failed to detect #[test] with #[ignore]"

    def test_test_attribute_order(self):
        """#[test] in any order in attribute list should work."""
        source = """
#[ignore]
#[test]
fn test_something() {
    assert!(true);
}
"""
        result = detect_test_function(source, "test_something", 2)
        assert result is True, "Failed to detect #[test] when not first attribute"


class TestFindCfgTestBlocks:
    """Test detection of #[cfg(test)] block boundaries."""

    def test_simple_cfg_test_block(self):
        """Simple #[cfg(test)] block should be detected."""
        source = """
pub fn public_fn() {}

#[cfg(test)]
mod tests {
    #[test]
    fn test_foo() {
        assert!(true);
    }
}
"""
        blocks = find_cfg_test_blocks(source)
        assert len(blocks) == 1, f"Expected 1 block, got {len(blocks)}"
        start, end = blocks[0]
        assert start <= 4, f"Block start should be <= 4, got {start}"
        assert end >= 8, f"Block end should be >= 8, got {end}"

    def test_no_cfg_test_block(self):
        """Source without #[cfg(test)] should return empty list."""
        source = """
pub fn foo() {}
pub fn bar() {}
"""
        blocks = find_cfg_test_blocks(source)
        assert blocks == [], f"Expected no blocks, got {blocks}"

    def test_multiple_cfg_test_blocks(self):
        """Multiple #[cfg(test)] blocks should all be detected."""
        source = """
#[cfg(test)]
mod tests1 {
    #[test]
    fn test_a() {}
}

pub fn middle() {}

#[cfg(test)]
mod tests2 {
    #[test]
    fn test_b() {}
}
"""
        blocks = find_cfg_test_blocks(source)
        assert len(blocks) == 2, f"Expected 2 blocks, got {len(blocks)}"

    def test_nested_cfg_test_blocks(self):
        """Nested #[cfg(test)] blocks should handle line ranges correctly."""
        source = """
#[cfg(test)]
mod outer {
    #[cfg(test)]
    mod inner {
        #[test]
        fn test_nested() {}
    }
}
"""
        blocks = find_cfg_test_blocks(source)
        # Should detect nested blocks (exact behavior depends on implementation)
        assert len(blocks) >= 1, f"Expected at least 1 block, got {len(blocks)}"


class TestNodeInCfgTestBlock:
    """Test membership checking for nodes in #[cfg(test)] blocks."""

    def test_node_inside_block(self):
        """Node at line inside block should return True."""
        source = """
#[cfg(test)]
mod tests {
    fn helper() {}
    #[test]
    fn test_foo() {}
}
"""
        blocks = find_cfg_test_blocks(source)
        # Node at line 3 (fn helper) should be inside the block
        result = node_in_cfg_test_block("L3", blocks)
        assert result is True, "Node inside block should return True"

    def test_node_outside_block(self):
        """Node at line outside block should return False."""
        source = """
pub fn not_test() {}

#[cfg(test)]
mod tests {
    #[test]
    fn test_foo() {}
}
"""
        blocks = find_cfg_test_blocks(source)
        # Node at line 1 should be outside
        result = node_in_cfg_test_block("L1", blocks)
        assert result is False, "Node outside block should return False"


class TestFilterGraphJson:
    """Test the main filtering function on graph.json structures."""

    def test_marks_test_function_nodes(self):
        """Test function nodes should be marked with is_test_function."""
        # Create minimal source file with test function
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            src_file = tmpdir / "lib.rs"
            src_file.write_text("""
#[test]
fn test_basic() {
    assert!(true);
}
""")

            nodes = [
                {
                    "label": "test_basic",
                    "file_type": "code",
                    "source_file": str(src_file),
                    "source_location": "L2",
                    "id": "test_basic",
                    "community": 0,
                }
            ]
            graph = make_test_graph(nodes)

            # Call filter function
            filtered = filter_graph_json(graph, str(tmpdir))

            # Check that node was marked
            assert filtered["nodes"][0].get("is_test_function") is True, \
                "Test function should be marked with is_test_function"

    def test_marks_cfg_test_scope(self):
        """Nodes in #[cfg(test)] should be marked with source_scope."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            src_file = tmpdir / "lib.rs"
            src_file.write_text("""
pub fn production() {}

#[cfg(test)]
mod tests {
    fn test_helper() {}
}
""")

            nodes = [
                {
                    "label": "production",
                    "file_type": "code",
                    "source_file": str(src_file),
                    "source_location": "L2",
                    "id": "production",
                    "community": 0,
                },
                {
                    "label": "test_helper",
                    "file_type": "code",
                    "source_file": str(src_file),
                    "source_location": "L6",
                    "id": "test_helper",
                    "community": 0,
                },
            ]
            graph = make_test_graph(nodes)

            # Call filter function
            filtered = filter_graph_json(graph, str(tmpdir))

            # Check scopes
            production_node = next(n for n in filtered["nodes"] if n["id"] == "production")
            test_node = next(n for n in filtered["nodes"] if n["id"] == "test_helper")

            assert production_node.get("source_scope") == "production", \
                "Production function should be marked as production scope"
            assert test_node.get("source_scope") == "test", \
                "Function in cfg(test) should be marked as test scope"

    def test_filter_output_structure(self):
        """Filtered graph should have the same structure with new attributes."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir = Path(tmpdir)
            src_file = tmpdir / "lib.rs"
            src_file.write_text("pub fn foo() {}")

            nodes = [
                {
                    "label": "foo",
                    "file_type": "code",
                    "source_file": str(src_file),
                    "source_location": "L1",
                    "id": "foo",
                    "community": 0,
                }
            ]
            graph = make_test_graph(nodes)

            filtered = filter_graph_json(graph, str(tmpdir))

            # Should preserve structure
            assert "nodes" in filtered
            assert "links" in filtered
            assert len(filtered["nodes"]) == len(nodes)

            # Should have added scope attribute
            assert filtered["nodes"][0].get("source_scope") in ["production", "test"]


class TestIsolatedNodeFiltering:
    """Test identification and filtering of isolated nodes by scope."""

    def test_isolated_node_count_by_scope(self):
        """Test that get_isolated_nodes_by_scope correctly separates nodes."""
        from scripts.graphify_filter_dead_code import get_isolated_nodes_by_scope
        import networkx as nx

        # Create a graph with isolated and non-isolated nodes
        G = nx.Graph()
        G.add_node("isolated_prod", source_scope="production", label="isolated_prod")
        G.add_node("isolated_test", source_scope="test", label="isolated_test")
        G.add_node("connected1", source_scope="production", label="connected1")
        G.add_node("connected2", source_scope="production", label="connected2")
        G.add_edge("connected1", "connected2")

        result = get_isolated_nodes_by_scope(G)

        assert result["production"] == ["isolated_prod"], \
            f"Expected 1 production isolated node, got {result['production']}"
        assert result["test"] == ["isolated_test"], \
            f"Expected 1 test isolated node, got {result['test']}"
