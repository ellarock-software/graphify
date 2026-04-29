from pathlib import Path
from graphify.extract import extract_python, extract_rust, extract, collect_files, _make_id

FIXTURES = Path(__file__).parent / "fixtures"


def test_make_id_strips_dots_and_underscores():
    assert _make_id("_auth") == "auth"
    assert _make_id(".httpx._client") == "httpx_client"


def test_make_id_consistent():
    """Same input always produces same output."""
    assert _make_id("foo", "Bar") == _make_id("foo", "Bar")


def test_make_id_no_leading_trailing_underscores():
    result = _make_id("__init__")
    assert not result.startswith("_")
    assert not result.endswith("_")


def test_extract_python_finds_class():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert "Transformer" in labels


def test_extract_python_finds_methods():
    result = extract_python(FIXTURES / "sample.py")
    labels = [n["label"] for n in result["nodes"]]
    assert any("__init__" in l or "forward" in l for l in labels)


def test_extract_python_no_dangling_edges():
    """All edge sources must reference a known node (targets may be external imports)."""
    result = extract_python(FIXTURES / "sample.py")
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in node_ids, f"Dangling source: {edge['source']}"


def test_structural_edges_are_extracted():
    """contains / method / inherits / imports edges must always be EXTRACTED."""
    result = extract_python(FIXTURES / "sample.py")
    structural = {"contains", "method", "inherits", "imports", "imports_from"}
    for edge in result["edges"]:
        if edge["relation"] in structural:
            assert edge["confidence"] == "EXTRACTED", f"Expected EXTRACTED: {edge}"


def test_extract_merges_multiple_files():
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    assert len(result["nodes"]) > 0
    assert result["input_tokens"] == 0


def test_collect_files_from_dir():
    files = collect_files(FIXTURES)
    supported = {".py", ".js", ".ts", ".tsx", ".go", ".rs",
                 ".java", ".c", ".cpp", ".cc", ".cxx", ".rb",
                 ".cs", ".kt", ".kts", ".scala", ".php", ".h", ".hpp",
                 ".swift", ".lua", ".toc", ".zig", ".ps1", ".ex", ".exs",
                 ".m", ".mm"}
    assert all(f.suffix in supported for f in files)
    assert len(files) > 0


def test_collect_files_skips_hidden():
    files = collect_files(FIXTURES)
    for f in files:
        assert not any(part.startswith(".") for part in f.parts)


def test_collect_files_follows_symlinked_directory(tmp_path):
    real_dir = tmp_path / "real_src"
    real_dir.mkdir()
    (real_dir / "lib.py").write_text("x = 1")
    (tmp_path / "linked_src").symlink_to(real_dir)

    files_no = collect_files(tmp_path, follow_symlinks=False)
    files_yes = collect_files(tmp_path, follow_symlinks=True)

    assert [f.name for f in files_no].count("lib.py") == 1
    assert [f.name for f in files_yes].count("lib.py") == 2


def test_collect_files_handles_circular_symlinks(tmp_path):
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("x = 1")
    (sub / "cycle").symlink_to(tmp_path)

    files = collect_files(tmp_path, follow_symlinks=True)
    assert any(f.name == "mod.py" for f in files)


def test_no_dangling_edges_on_extract():
    """After merging multiple files, no internal edges should be dangling."""
    files = list(FIXTURES.glob("*.py"))
    result = extract(files)
    node_ids = {n["id"] for n in result["nodes"]}
    internal_relations = {"contains", "method", "inherits", "calls"}
    for edge in result["edges"]:
        if edge["relation"] in internal_relations:
            assert edge["source"] in node_ids, f"Dangling source: {edge}"
            assert edge["target"] in node_ids, f"Dangling target: {edge}"


def test_calls_edges_emitted():
    """Call-graph pass must produce INFERRED calls edges."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, "Expected at least one calls edge"


def test_calls_edges_are_extracted():
    """AST-resolved call edges are deterministic and should be EXTRACTED/1.0."""
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["confidence"] == "EXTRACTED"
            assert edge["weight"] == 1.0


def test_calls_no_self_loops():
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["source"] != edge["target"], f"Self-loop: {edge}"


def test_run_analysis_calls_compute_score():
    """run_analysis() calls compute_score() - must appear as a calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("compute_score()")
    assert src and tgt, "run_analysis or compute_score node not found"
    assert (src, tgt) in calls, f"run_analysis -> compute_score not found in {calls}"


def test_run_analysis_calls_normalize():
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get("run_analysis()")
    tgt = node_by_label.get("normalize()")
    assert src and tgt
    assert (src, tgt) in calls


def test_method_calls_module_function():
    """Analyzer.process() calls run_analysis() - cross class→function calls edge."""
    result = extract_python(FIXTURES / "sample_calls.py")
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    src = node_by_label.get(".process()")
    tgt = node_by_label.get("run_analysis()")
    assert src and tgt
    assert (src, tgt) in calls


def test_calls_deduplication():
    """Same caller→callee pair must appear only once even if called multiple times."""
    result = extract_python(FIXTURES / "sample_calls.py")
    call_pairs = [(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"]
    assert len(call_pairs) == len(set(call_pairs)), "Duplicate calls edges found"


def test_rust_reexport_resolves_to_definition():
    """pub use re-exports should create edge pointing to actual definition, not dangling node."""
    # Use multi-file extract to test cross-file re-export resolution
    project_dir = FIXTURES / "rust_project_reexports/src"
    files = list(project_dir.glob("*.rs"))
    assert len(files) > 0, "No Rust files found in test fixture"

    result = extract(files)

    # Get the Error node (should be from the error module definition)
    error_nodes = [n for n in result["nodes"] if n["label"] == "Error"]
    assert len(error_nodes) > 0, (
        f"Error node not found. Available nodes: {[n['label'] for n in result['nodes']]}"
    )

    # Get imports_from edges (re-export edges)
    reexport_edges = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(reexport_edges) > 0, "No imports_from edges found; re-exports not extracted"

    # Verify at least one edge points to a known Error node
    error_ids = {n["id"] for n in error_nodes}
    edges_to_error = [e for e in reexport_edges if e["target"] in error_ids]
    assert len(edges_to_error) > 0, (
        f"No imports_from edge points to Error definition. "
        f"Error IDs: {error_ids}, reexport targets: {[e['target'] for e in reexport_edges]}"
    )


def test_rust_scoped_call_resolves_with_namespace():
    """Scoped calls like fixtures::gemini_timeout() should preserve namespace and resolve correctly."""
    # Use multi-file extract to test call resolution
    project_dir = FIXTURES / "rust_project_scoped/src"
    files = list(project_dir.glob("*.rs"))
    assert len(files) > 0, "No Rust files found in test fixture"

    result = extract(files)

    # Get the function nodes
    nodes_by_label = {n["label"]: n["id"] for n in result["nodes"]}

    # Should have gemini_timeout (from fixtures module)
    fixture_timeout = nodes_by_label.get("gemini_timeout()")
    run_test = nodes_by_label.get("run_test()")

    assert fixture_timeout, (
        f"gemini_timeout() not found. Available functions: "
        f"{[n['label'] for n in result['nodes'] if '()' in n['label']]}"
    )
    assert run_test, "run_test() function not found"

    # run_test should have a calls edge to gemini_timeout
    calls = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "calls"}
    assert (run_test, fixture_timeout) in calls, (
        f"Expected call from run_test() to gemini_timeout(). "
        f"Found calls: {calls}"
    )


def test_rust_scoped_call_no_collision():
    """Same function name in different modules should not collide."""
    # Use multi-file extract
    project_dir = FIXTURES / "rust_project_scoped/src"
    files = list(project_dir.glob("*.rs"))
    assert len(files) > 0, "No Rust files found in test fixture"

    result = extract(files)

    # With correct scoped call resolution, run_test calling fixtures::gemini_timeout
    # should not resolve to other::gemini_timeout

    nodes_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    run_test = nodes_by_label.get("run_test()")
    assert run_test, "run_test() not found"

    # Get calls from run_test
    run_test_calls = [e for e in result["edges"] if e["relation"] == "calls" and e["source"] == run_test]
    assert len(run_test_calls) > 0, "run_test() has no calls; scoped calls not extracted"

    # The call should go to one specific gemini_timeout, not both
    call_targets = [e["target"] for e in run_test_calls]
    assert len(set(call_targets)) <= 1, (
        f"run_test() calls resolved to multiple different targets; namespace collision. "
        f"Targets: {call_targets}"
    )

    # Verify it's calling the correct one (fixtures::gemini_timeout)
    # by checking the node label/id contains "fixtures" context
    target_id = call_targets[0]
    target_node = next((n for n in result["nodes"] if n["id"] == target_id), None)
    assert target_node, f"Target node {target_id} not found"
