import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ConfigurationError, load_config, validate_port
from serv_fich_multithread import is_authenticated


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

    def test_authentication_requires_non_empty_privileged_password(self):
        passwords = ("", "configured-secret")

        self.assertTrue(is_authenticated(0, "", passwords))
        self.assertFalse(is_authenticated(1, "", ("", "")))
        self.assertTrue(is_authenticated(1, "configured-secret", passwords))
        self.assertFalse(is_authenticated(1, "wrong", passwords))


if __name__ == "__main__":
    unittest.main()