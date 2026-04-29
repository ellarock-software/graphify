"""MAN-153: implicit-call edges so unittest/pytest test methods aren't isolated.

Without these edges, every test method extracted by graphify has degree 1 (only
the class→method `method` edge), so it is flagged as an isolated knowledge gap
even though the test runner — not in-source code — invokes it.
"""
import textwrap
from pathlib import Path
from graphify.extract import extract_python


def _write_py(tmp_path: Path, code: str, name: str = "sample.py") -> Path:
    p = tmp_path / name
    p.write_text(textwrap.dedent(code))
    return p


def _implicit_call_targets(result, file_label: str) -> set[str]:
    """Return the set of node labels reachable from the file node via implicit_call edges."""
    file_ids = {n["id"] for n in result["nodes"] if n["label"] == file_label}
    label_by_id = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        label_by_id[e["target"]]
        for e in result["edges"]
        if e.get("relation") == "implicit_call"
        and e["source"] in file_ids
        and e["target"] in label_by_id
    }


def test_unittest_test_method_gets_implicit_call_edge(tmp_path):
    path = _write_py(tmp_path, '''
        import unittest
        class MyTests(unittest.TestCase):
            def test_thing(self):
                pass
    ''', name="test_thing.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_thing.py")
    assert ".test_thing()" in targets


def test_unittest_setup_teardown_get_implicit_call_edge(tmp_path):
    path = _write_py(tmp_path, '''
        import unittest
        class MyTests(unittest.TestCase):
            def setUp(self): pass
            def setUpClass(cls): pass
            def tearDown(self): pass
            def tearDownClass(cls): pass
            def test_x(self): pass
    ''', name="test_setup.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_setup.py")
    for label in (".setUp()", ".setUpClass()", ".tearDown()", ".tearDownClass()", ".test_x()"):
        assert label in targets, f"missing implicit_call to {label}; got {targets}"


def test_unittest_unqualified_testcase_base_recognized(tmp_path):
    path = _write_py(tmp_path, '''
        from unittest import TestCase
        class MyTests(TestCase):
            def test_thing(self):
                pass
    ''', name="test_unqual.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_unqual.py")
    assert ".test_thing()" in targets


def test_non_testcase_class_methods_no_implicit_call(tmp_path):
    path = _write_py(tmp_path, '''
        class Helper:
            def test_thing(self): pass
            def setUp(self): pass
    ''', name="helper.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "helper.py")
    assert ".test_thing()" not in targets
    assert ".setUp()" not in targets


def test_unittest_non_test_method_does_not_get_implicit_call(tmp_path):
    """Helper methods on TestCase subclasses (non-test, non-setup) shouldn't be marked reachable."""
    path = _write_py(tmp_path, '''
        import unittest
        class MyTests(unittest.TestCase):
            def helper_method(self): pass
            def test_real(self): pass
    ''', name="test_helper.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_helper.py")
    assert ".test_real()" in targets
    assert ".helper_method()" not in targets


def test_pytest_module_test_function_gets_implicit_call_edge(tmp_path):
    path = _write_py(tmp_path, '''
        def test_something():
            assert True
    ''', name="test_module.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_module.py")
    assert "test_something()" in targets


def test_pytest_underscore_test_suffix_recognized(tmp_path):
    path = _write_py(tmp_path, '''
        def test_thing():
            pass
    ''', name="thing_test.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "thing_test.py")
    assert "test_thing()" in targets


def test_pytest_no_edge_in_non_test_file(tmp_path):
    """A function named test_* in helpers.py shouldn't get an implicit_call edge."""
    path = _write_py(tmp_path, '''
        def test_helper():
            pass
    ''', name="helpers.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "helpers.py")
    assert "test_helper()" not in targets


def test_pytest_no_edge_for_non_test_function_in_test_file(tmp_path):
    path = _write_py(tmp_path, '''
        def helper():
            pass
        def test_real():
            helper()
    ''', name="test_mixed.py")
    result = extract_python(path)
    targets = _implicit_call_targets(result, "test_mixed.py")
    assert "test_real()" in targets
    assert "helper()" not in targets


def test_implicit_call_edge_confidence_is_extracted(tmp_path):
    path = _write_py(tmp_path, '''
        import unittest
        class MyTests(unittest.TestCase):
            def test_thing(self): pass
    ''', name="test_conf.py")
    result = extract_python(path)
    impl = [e for e in result["edges"] if e.get("relation") == "implicit_call"]
    assert impl, "expected at least one implicit_call edge"
    assert all(e.get("confidence") == "EXTRACTED" for e in impl)
