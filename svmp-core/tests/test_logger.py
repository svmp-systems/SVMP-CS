"""Sanity tests for the shared logger bootstrap."""

from __future__ import annotations

from svmp_core.logger import get_logger


def test_get_logger_emits_bound_context(capsys) -> None:
    """Logger output should include shared app context and event data."""

    logger = get_logger("svmp.tests")

    logger.info("logger_test", component="tests")

    captured = capsys.readouterr()
    output = captured.out.strip()

    assert output
    assert '"event": "logger_test"' in output
    assert '"component": "tests"' in output
    assert '"app": "SVMP"' in output
    assert '"env": "development"' in output
