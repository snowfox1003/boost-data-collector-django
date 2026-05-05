"""Smoke test for root ``test_workspace_dir`` session fixture (see conftest.py)."""


def test_test_workspace_dir_resolves_to_path(test_workspace_dir):
    assert str(test_workspace_dir)
