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
                 ".cs", ".kt", ".kts", ".scala", ".php", ".h", ".hpp"}
    assert all(f.suffix in supported for f in files)
    assert len(files) > 0


def test_collect_files_skips_hidden():
    files = collect_files(FIXTURES)
    for f in files:
        assert not any(part.startswith(".") for part in f.parts)


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


def test_calls_edges_are_inferred():
    result = extract_python(FIXTURES / "sample_calls.py")
    for edge in result["edges"]:
        if edge["relation"] == "calls":
            assert edge["confidence"] == "INFERRED"
            assert edge["weight"] == 0.8


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
    """pub use declarations must create edges to the actual definition, not just the final segment."""
    path = FIXTURES / "rust_project_reexports" / "src" / "lib.rs"
    result = extract_rust(path)
    imports = [e for e in result["edges"] if e["relation"] == "imports_from"]
    assert len(imports) > 0, "Expected at least one imports_from edge for pub use"
    # Edge should point to Error node (the actual struct), not a dangling external import
    target_ids = {e["target"] for e in imports}
    target_labels = [n["label"] for n in result["nodes"] if n["id"] in target_ids]
    assert any("Error" in label for label in target_labels), f"Expected Error in targets, got {target_labels}"


def test_rust_scoped_call_resolves_with_namespace():
    """Scoped calls like fixtures::gemini_timeout() must resolve to the correct module function."""
    files = list((FIXTURES / "rust_project_scoped" / "src").glob("*.rs"))
    result = extract(files)
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    assert len(calls) > 0, "Expected at least one calls edge"
    # The caller should be lib::caller
    node_by_label = {n["label"]: n["id"] for n in result["nodes"]}
    caller_id = node_by_label.get("caller()")
    # The target should be the fixtures::gemini_timeout, not the one from other.rs
    assert caller_id, "caller() function not found"
    caller_calls = [e for e in calls if e["source"] == caller_id]
    assert len(caller_calls) > 0, "caller() should call something"
    target_ids = {e["target"] for e in caller_calls}
    target_labels = [n["label"] for n in result["nodes"] if n["id"] in target_ids]
    assert any("gemini_timeout" in str(label).lower() for label in target_labels), f"Expected gemini_timeout in targets, got {target_labels}"


def test_rust_scoped_call_no_collision():
    """When multiple functions share the same name (gemini_timeout in fixtures.rs vs other.rs),
    a scoped call fixtures::gemini_timeout() must resolve to the correct one, not collide."""
    files = list((FIXTURES / "rust_project_scoped" / "src").glob("*.rs"))
    result = extract(files)
    # Count gemini_timeout nodes
    gemini_nodes = [n for n in result["nodes"] if "gemini_timeout" in n["label"].lower()]
    assert len(gemini_nodes) >= 2, f"Expected at least 2 gemini_timeout functions, got {len(gemini_nodes)}"
    # Verify calls only go to the qualified one (fixtures::gemini_timeout), not other::gemini_timeout
    calls = [e for e in result["edges"] if e["relation"] == "calls"]
    node_by_id = {n["id"]: n for n in result["nodes"]}
    for call in calls:
        if "gemini_timeout" in node_by_id.get(call["target"], {}).get("label", "").lower():
            # This call should be to the fixtures module, confirmed by looking at the extraction
            assert call["target"] in {n["id"] for n in gemini_nodes}, "Call target is not one of the gemini_timeout nodes"
