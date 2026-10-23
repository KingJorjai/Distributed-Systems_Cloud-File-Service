import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cli_fich import parse_client_args
from config import ConfigurationError, load_config, validate_port
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