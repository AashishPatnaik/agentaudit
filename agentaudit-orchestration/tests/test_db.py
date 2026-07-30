from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentaudit_orchestration.db import get_audit_connection


def _mock_connection():
    cursor = MagicMock()
    cursor.__enter__.return_value = cursor
    cursor.__exit__.return_value = False

    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


@patch("agentaudit_orchestration.db._connect")
def test_set_transaction_read_write_runs_before_callers_write_then_commits(mock_connect):
    conn, cursor = _mock_connection()
    mock_connect.return_value = conn

    with get_audit_connection() as yielded_conn, yielded_conn.cursor() as cur:
        cur.execute("INSERT INTO audit_log VALUES (%s)", ("row",))

    # Two cursor().execute() calls happened on the same underlying cursor
    # mock: get_audit_connection's own SET TRANSACTION READ WRITE, then the
    # caller's write. Order matters — it must run first, as the first
    # statement of the transaction, in the same transaction as the write.
    assert cursor.execute.call_args_list == [
        (("SET TRANSACTION READ WRITE",), {}),
        (("INSERT INTO audit_log VALUES (%s)", ("row",)), {}),
    ]
    conn.commit.assert_called_once()
    conn.rollback.assert_not_called()
    conn.close.assert_called_once()


@patch("agentaudit_orchestration.db._connect")
def test_callers_write_failure_rolls_back_and_reraises(mock_connect):
    conn, cursor = _mock_connection()
    mock_connect.return_value = conn

    class BoomError(Exception):
        pass

    with pytest.raises(BoomError):
        with get_audit_connection() as yielded_conn:
            raise BoomError("write failed")

    conn.rollback.assert_called_once()
    conn.commit.assert_not_called()
    conn.close.assert_called_once()
