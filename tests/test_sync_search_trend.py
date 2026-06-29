from unittest.mock import MagicMock, patch

import pytest

from mim import sync_search_trend

_NAVER_ENV = {"NAVER_CLIENT_ID": "id", "NAVER_CLIENT_SECRET": "secret"}
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
    return patch("mim.sync_search_trend.dotenv_values", return_value={})


class TestLoadEnv:
    def test_database_url_skips_ssh_keys(self):
        env = {**_NAVER_ENV, "DATABASE_URL": "postgres://u:p@host/db"}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            result = sync_search_trend.load_env()
        assert result["DATABASE_URL"] == "postgres://u:p@host/db"

    def test_no_database_url_requires_ssh_keys(self):
        env = {**_NAVER_ENV, **_SSH_ENV}
        with _patch_dotenv(), patch.dict("os.environ", env, clear=True):
            result = sync_search_trend.load_env()
        assert result["SSH_HOST"] == "bastion"

    def test_missing_naver_key_raises(self):
        with _patch_dotenv(), patch.dict("os.environ", {"DATABASE_URL": "postgres://u:p@h/db"}, clear=True):
            with pytest.raises(RuntimeError, match="NAVER_CLIENT_ID"):
                sync_search_trend.load_env()

    def test_missing_ssh_keys_without_database_url_raises(self):
        with _patch_dotenv(), patch.dict("os.environ", _NAVER_ENV, clear=True):
            with pytest.raises(RuntimeError):
                sync_search_trend.load_env()


class TestConnectDb:
    def test_direct_connection_when_database_url_set(self):
        env = {"DATABASE_URL": "postgres://u:p@host/db"}
        mock_conn = MagicMock()
        with patch("mim.sync_search_trend.psycopg2.connect", return_value=mock_conn) as mock_connect:
            with sync_search_trend.connect_db(env) as conn:
                assert conn is mock_conn
        mock_connect.assert_called_once_with("postgres://u:p@host/db")
        mock_conn.close.assert_called_once()

    def test_direct_connection_closes_on_exception(self):
        env = {"DATABASE_URL": "postgres://u:p@host/db"}
        mock_conn = MagicMock()
        with patch("mim.sync_search_trend.psycopg2.connect", return_value=mock_conn):
            with pytest.raises(ValueError):
                with sync_search_trend.connect_db(env):
                    raise ValueError("boom")
        mock_conn.close.assert_called_once()

    def test_ssh_tunnel_when_no_database_url(self):
        mock_conn = MagicMock()
        mock_tunnel = MagicMock()
        mock_tunnel.__enter__.return_value = mock_tunnel
        mock_tunnel.local_bind_port = 55432

        with patch("mim.sync_search_trend.SSHTunnelForwarder", return_value=mock_tunnel), \
             patch("mim.sync_search_trend.psycopg2.connect", return_value=mock_conn) as mock_connect:
            with sync_search_trend.connect_db(_SSH_ENV) as conn:
                assert conn is mock_conn

        mock_connect.assert_called_once_with(
            host="127.0.0.1",
            port=55432,
            dbname="postgres",
            user="dbuser",
            password="dbpass",
        )
        mock_conn.close.assert_called_once()
