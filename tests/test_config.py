import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli_fich import parse_client_args
from config import (
    ConfigurationError,
    default_config_path,
    load_config,
    save_client_config,
    validate_port,
)
from file_store import FileStore, InvalidPasswordError


class LoadConfigTests(unittest.TestCase):
    def write_config(self, content):
        config_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.addCleanup(lambda: Path(config_file.name).unlink(missing_ok=True))
        config_file.write(content)
        config_file.close()
        return config_file.name

    def test_reads_values_from_toml(self):
        path = self.write_config(
            '[client]\nserver = "configured-server"\nport = 6100\n'
            'local_path = "configured-client"\n\n'
            '[server]\nport = 6200\nfiles_path = "configured-server-files"\n'
            'max_file_size = 100\nspace_margin = 200\n'
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path)

        self.assertEqual(config.client.server, "configured-server")
        self.assertEqual(config.client.port, 6100)
        self.assertEqual(config.server.files_path, "configured-server-files")
        self.assertEqual(config.server.space_margin, 200)

    def test_environment_overrides_toml(self):
        path = self.write_config('[client]\nport = 6100\n')

        with patch.dict(os.environ, {"CLIENT_PORT": "6300"}, clear=False):
            config = load_config(path)

        self.assertEqual(config.client.port, 6300)

    def test_rejects_invalid_port(self):
        path = self.write_config('[server]\nport = 70000\n')

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_rejects_boolean_and_float_values(self):
        for value in ("true", "1.5"):
            path = self.write_config(f"[server]\nport = {value}\n")
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                load_config(path)

    def test_rejects_non_table_section(self):
        path = self.write_config('client = "invalid"\n')

        with self.assertRaises(ConfigurationError):
            load_config(path)

    def test_validates_cli_port_values(self):
        self.assertEqual(validate_port("6200"), 6200)
        for value in ("0", "65536", "not-a-port"):
            with self.subTest(value=value), self.assertRaises(ConfigurationError):
                validate_port(value)

    def test_bootstrap_user_authentication(self):
        with tempfile.TemporaryDirectory() as directory:
            store = FileStore(directory)
            self.addCleanup(store.close)
            store.ensure_bootstrap_user("sar", "configured-secret", "admin")

            self.assertEqual(
                store.authenticate("sar", "configured-secret").role, "admin"
            )
            with self.assertRaises(InvalidPasswordError):
                store.authenticate("sar", "wrong")

    def test_reads_tls_and_state_settings(self):
        path = self.write_config(
            '[client]\n'
            'tls_ca_file = "ca.crt"\n'
            'tls_server_name = "cloud.example"\n'
            'state_dir = "/tmp/cloudfs-state"\n'
            '\n[server]\n'
            'host = "127.0.0.1"\n'
            'tls_cert_file = "server.crt"\n'
            'tls_key_file = "server.key"\n'
            'tls_ca_file = "ca.crt"\n'
            'registration_enabled = false\n'
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path)

        self.assertEqual(config.client.tls_ca_file, "ca.crt")
        self.assertEqual(config.client.tls_server_name, "cloud.example")
        self.assertEqual(config.client.state_dir, "/tmp/cloudfs-state")
        self.assertEqual(config.server.host, "127.0.0.1")
        self.assertFalse(config.server.registration_enabled)

    def test_tls_env_overrides_toml(self):
        path = self.write_config('[server]\ntls_cert_file = "old.crt"\n')

        with patch.dict(os.environ, {"TLS_CERT_FILE": "new.crt"}, clear=False):
            self.assertEqual(load_config(path).server.tls_cert_file, "new.crt")

    def test_reads_replication_settings(self):
        path = self.write_config(
            '[server]\n'
            'server_id = "server1"\n'
            'role = "primary"\n'
            'peers = "server2@host2:60012,server3@host3:60012"\n'
            'primary = "server1@host1:60012"\n'
            'replication_host = "127.0.0.1"\n'
            'replication_port = 61012\n'
            'cluster_token = "secret"\n'
            'term = 3\n'
            'replication_timeout = 1.5\n'
        )
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path)

        self.assertEqual(config.server.server_id, "server1")
        self.assertEqual(config.server.role, "primary")
        self.assertIn("server2@host2", config.server.peers)
        self.assertEqual(config.server.replication_port, 61012)
        self.assertEqual(config.server.term, 3)
        self.assertEqual(config.server.replication_timeout, 1.5)

    def test_reads_election_and_client_peers(self):
        path = self.write_config(
            '[client]\npeers = "s1:50012,s2:50012"\n\n'
            '[server]\nheartbeat_interval = 0.2\nfailure_timeout = 1.0\n'
            'election_timeout = 0.4\n'
            'client_addresses = "server1@s1:50012,server2@s2:50012"\n'
        )
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path)

        self.assertEqual(config.client.peers, "s1:50012,s2:50012")
        self.assertEqual(config.server.heartbeat_interval, 0.2)
        self.assertEqual(config.server.failure_timeout, 1.0)
        self.assertEqual(config.server.election_timeout, 0.4)
        self.assertIn("server2@s2", config.server.client_addresses)

    def test_reads_admin_settings(self):
        path = self.write_config(
            '[server]\nadmin_enabled = true\nadmin_host = "0.0.0.0"\n'
            'admin_port = 50081\nadmin_addresses = "server1@host1:50081"\n'
            'allow_admin_failover = true\nadmin_session_timeout = 60\n'
        )
        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path)

        self.assertTrue(config.server.admin_enabled)
        self.assertEqual(config.server.admin_host, "0.0.0.0")
        self.assertEqual(config.server.admin_port, 50081)
        self.assertTrue(config.server.allow_admin_failover)
        self.assertEqual(config.server.admin_session_timeout, 60.0)

    def test_rejects_invalid_role(self):
        path = self.write_config('[server]\nrole = "leader"\n')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_rejects_invalid_replication_port(self):
        path = self.write_config('[server]\nreplication_port = 0\n')
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_save_client_config_preserves_server_section(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.toml"
            path.write_text("[server]\nport = 6200\n", encoding="utf-8")
            config = load_config(path).client
            from dataclasses import replace

            save_client_config(path, replace(config, server="example", port=6300))

            restored = load_config(path)
            self.assertEqual(restored.client.server, "example")
            self.assertEqual(restored.client.port, 6300)
            self.assertEqual(restored.server.port, 6200)

    def test_default_config_path_is_under_user_config(self):
        self.assertTrue(str(default_config_path()).endswith("config.toml"))

    def test_rejects_invalid_registration_boolean(self):
        path = self.write_config('[server]\nregistration_enabled = "sometimes"\n')

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigurationError):
                load_config(path)


class ParseClientArgsTests(unittest.TestCase):
    def write_config(self, content):
        config_file = tempfile.NamedTemporaryFile(mode="w", delete=False)
        self.addCleanup(lambda: Path(config_file.name).unlink(missing_ok=True))
        config_file.write(content)
        config_file.close()
        return config_file.name

    def test_parses_server_port_and_local_path(self):
        path = self.write_config(
            '[client]\nserver = "configured-server"\nport = 6100\n'
            'local_path = "configured-client"\n'
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path).client

        server, port, local_path = parse_client_args(
            ["cli_fich.py", "example", "6200", "custom-dir"], config
        )
        self.assertEqual((server, port, local_path), ("example", 6200, "custom-dir"))

    def test_defaults_come_from_configuration(self):
        path = self.write_config(
            '[client]\nserver = "configured-server"\nport = 6100\n'
            'local_path = "configured-client"\n'
        )

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path).client

        self.assertEqual(
            parse_client_args(["cli_fich.py"], config),
            ("configured-server", 6100, "configured-client"),
        )

    def test_rejects_invalid_port(self):
        path = self.write_config('[client]\nport = 6100\n')

        with patch.dict(os.environ, {}, clear=True):
            config = load_config(path).client

        with self.assertRaises(SystemExit):
            parse_client_args(["cli_fich.py", "example", "not-a-port"], config)


if __name__ == "__main__":
    unittest.main()