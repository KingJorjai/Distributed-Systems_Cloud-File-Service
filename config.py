"""Application configuration loaded from TOML and environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

DEFAULT_CONFIG_FILE = "config.toml"


class ConfigurationError(ValueError):
    """Raised when application configuration is invalid."""


@dataclass(frozen=True)
class ClientConfig:
    server: str = "localhost"
    port: int = 50012
    local_path: str = "client_files"
    tls_ca_file: str = ""
    tls_server_name: str = ""
    state_dir: str = ""


@dataclass(frozen=True)
class ServerConfig:
    host: str = ""
    port: int = 50012
    files_path: str = "files"
    tls_cert_file: str = "certs/server.crt"
    tls_key_file: str = "certs/server.key"
    tls_ca_file: str = "certs/ca.crt"
    registration_enabled: bool = True
    max_file_size: int = 10 * 1 << 20
    space_margin: int = 50 * 1 << 20


@dataclass(frozen=True)
class AppConfig:
    client: ClientConfig
    server: ServerConfig
    passwords: dict[str, str]


def _read_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as config_file:
            return tomllib.load(config_file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationError(f"Invalid TOML configuration: {path}") from error


def _value(data: dict, section: str, key: str, env_name: str, default):
    value = os.environ.get(env_name)
    if value is not None:
        return value
    section_data = data.get(section, {})
    if not isinstance(section_data, dict):
        raise ConfigurationError(f"[{section}] must be a TOML table")
    return section_data.get(key, default)


def _integer(value, name: str) -> int:
    if isinstance(value, bool):
        raise ConfigurationError(f"{name} must be an integer")
    if not isinstance(value, (int, str)):
        raise ConfigurationError(f"{name} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{name} must be an integer") from error
    if result < 1:
        raise ConfigurationError(f"{name} must be greater than zero")
    return result


def validate_port(value) -> int:
    """Convert and validate a TCP port from configuration or CLI input."""
    port = _integer(value, "port")
    if port > 65535:
        raise ConfigurationError("port must be between 1 and 65535")
    return port


def _boolean(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ConfigurationError(f"{name} must be a boolean")


def load_config(path: str | os.PathLike[str] | None = None) -> AppConfig:
    """Load configuration using environment variables as the highest override."""
    config_path = Path(path or os.environ.get("CONFIG_FILE", DEFAULT_CONFIG_FILE))
    data = _read_toml(config_path)

    client_port = validate_port(
        _value(data, "client", "port", "CLIENT_PORT", 50012)
    )
    server_port = validate_port(
        _value(data, "server", "port", "SERVER_PORT", 50012)
    )

    return AppConfig(
        client=ClientConfig(
            server=str(_value(data, "client", "server", "CLIENT_SERVER", "localhost")),
            port=client_port,
            local_path=str(
                _value(
                    data, "client", "local_path", "CLIENT_LOCAL_PATH", "client_files"
                )
            ),
            tls_ca_file=str(
                _value(data, "client", "tls_ca_file", "CLIENT_TLS_CA_FILE", "")
            ),
            tls_server_name=str(
                _value(
                    data, "client", "tls_server_name", "CLIENT_TLS_SERVER_NAME", ""
                )
            ),
            state_dir=str(
                _value(data, "client", "state_dir", "CLIENT_STATE_DIR", "")
            ),
        ),
        server=ServerConfig(
            host=str(_value(data, "server", "host", "SERVER_HOST", "")),
            port=server_port,
            files_path=str(
                _value(data, "server", "files_path", "SERVER_FILES_PATH", "files")
            ),
            tls_cert_file=str(
                _value(data, "server", "tls_cert_file", "TLS_CERT_FILE", "certs/server.crt")
            ),
            tls_key_file=str(
                _value(data, "server", "tls_key_file", "TLS_KEY_FILE", "certs/server.key")
            ),
            tls_ca_file=str(
                _value(data, "server", "tls_ca_file", "TLS_CA_FILE", "certs/ca.crt")
            ),
            registration_enabled=_boolean(
                _value(
                    data,
                    "server",
                    "registration_enabled",
                    "ALLOW_REGISTRATION",
                    True,
                ),
                "ALLOW_REGISTRATION",
            ),
            max_file_size=_integer(
                _value(data, "server", "max_file_size", "MAX_FILE_SIZE", 10 * 1 << 20),
                "MAX_FILE_SIZE",
            ),
            space_margin=_integer(
                _value(data, "server", "space_margin", "SPACE_MARGIN", 50 * 1 << 20),
                "SPACE_MARGIN",
            ),
        ),
        passwords={
            "sar": os.environ.get("APP_PASSWORD_SAR", ""),
            "sza": os.environ.get("APP_PASSWORD_SZA", ""),
        },
    )