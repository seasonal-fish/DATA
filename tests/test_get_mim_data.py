"""
mim/get_mim_data.py 유닛 테스트
외부 의존성(Selenium, psycopg2, sshtunnel) 없이 실행 가능한 함수만 대상으로 함
"""
from unittest.mock import MagicMock, call, patch

import pytest

from mim import get_mim_data

_CAREET_ENV = {"CAREET_EMAIL": "user@example.com", "CAREET_PASSWORD": "secret"}
_SSH_ENV = {
    "SSH_HOST": "bastion",
    "SSH_PORT": "22",
    "SSH_USER": "ec2-user",
    "SSH_PEM_PATH": "/key.pem",
    "DB_HOST": "10.0.0.1",
    "DB_PORT": "5432",
    "DB_NAME": "postgres",
    "DB_USER": "dbuser",
    "DB_PASSWORD": "dbpass",
}


def _patch_dotenv():
    return patch("mim.get_mim_data.dotenv_values", return_value={})


# ---------------------------------------------------------------------------
# load_env
# ---------------------------------------------------------------------------

class TestLoadEnv:
    def test_database_url_skips_ssh_keys(self):
        env = {**_CAREET_ENV, "DATABASE_URL": "postgres://u:p@host/db"}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            result = get_mim_data.load_env()
        assert result["DATABASE_URL"] == "postgres://u:p@host/db"

    def test_missing_careet_email_raises(self):
        env = {"CAREET_PASSWORD": "secret", "DATABASE_URL": "postgres://u:p@h/db"}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            with pytest.raises(RuntimeError, match="CAREET_EMAIL"):
                get_mim_data.load_env()

    def test_missing_careet_password_raises(self):
        env = {"CAREET_EMAIL": "user@example.com", "DATABASE_URL": "postgres://u:p@h/db"}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            with pytest.raises(RuntimeError, match="CAREET_PASSWORD"):
                get_mim_data.load_env()

    def test_no_database_url_requires_ssh_keys(self):
        env = {**_CAREET_ENV, **_SSH_ENV}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            result = get_mim_data.load_env()
        assert result["SSH_HOST"] == "bastion"

    def test_no_database_url_missing_ssh_raises(self):
        with _patch_dotenv(), patch.dict("os.environ", _CAREET_ENV, clear=True):
            with pytest.raises(RuntimeError, match="SSH"):
                get_mim_data.load_env()


# ---------------------------------------------------------------------------
# connect_db
# ---------------------------------------------------------------------------

class TestConnectDb:
    def test_direct_connection_when_database_url_set(self):
        env = {"DATABASE_URL": "postgres://u:p@host/db"}
        mock_conn = MagicMock()
        with patch("mim.get_mim_data.psycopg2.connect", return_value=mock_conn) as mock_connect:
            conn, tunnel = get_mim_data.connect_db(env)
        assert conn is mock_conn
        assert tunnel is None
        mock_connect.assert_called_once_with("postgres://u:p@host/db")

    def test_ssh_tunnel_when_no_database_url(self):
        mock_conn = MagicMock()
        mock_tunnel = MagicMock()
        mock_tunnel.local_bind_port = 55432

        with patch("mim.get_mim_data.SSHTunnelForwarder", return_value=mock_tunnel), \
             patch("mim.get_mim_data.psycopg2.connect", return_value=mock_conn) as mock_connect:
            conn, tunnel = get_mim_data.connect_db(_SSH_ENV)

        assert conn is mock_conn
        assert tunnel is mock_tunnel
        mock_tunnel.start.assert_called_once()
        mock_connect.assert_called_once_with(
            host="127.0.0.1",
            port=55432,
            dbname="postgres",
            user="dbuser",
            password="dbpass",
        )


# ---------------------------------------------------------------------------
# upsert_terms
# ---------------------------------------------------------------------------

class TestUpsertTerms:
    def _make_conn(self):
        mock_cur = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cur)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        return mock_conn, mock_cur

    def test_executemany_called_with_rows(self):
        mock_conn, mock_cur = self._make_conn()
        rows = [
            {"word": "갓생", "definition": "부지런하게 사는 삶"},
            {"word": "스불재", "definition": "스스로 불러온 재앙"},
        ]
        get_mim_data.upsert_terms(mock_conn, rows)
        mock_cur.executemany.assert_called_once()
        _, call_args = mock_cur.executemany.call_args
        assert call_args == (rows,) or mock_cur.executemany.call_args[0][1] == rows

    def test_commit_called(self):
        mock_conn, _ = self._make_conn()
        get_mim_data.upsert_terms(mock_conn, [{"word": "w", "definition": "d"}])
        mock_conn.commit.assert_called_once()

    def test_empty_rows_still_commits(self):
        mock_conn, mock_cur = self._make_conn()
        get_mim_data.upsert_terms(mock_conn, [])
        mock_cur.executemany.assert_called_once()
        mock_conn.commit.assert_called_once()
