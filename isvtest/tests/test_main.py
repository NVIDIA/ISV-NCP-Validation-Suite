"""Dummy test to ensure pytest runs successfully."""

import isvtest.main


def test_dummy() -> None:
    """A simple dummy test that always passes."""
    assert True


def test_main_module_exists() -> None:
    """Test that the main module can be imported."""
    assert isvtest.main is not None
