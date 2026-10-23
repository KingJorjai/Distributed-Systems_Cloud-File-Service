"""Application configuration loaded from TOML and environment variables."""

import os
from dataclasses import dataclass
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

DEFAULT_CONFIG_FILE = "config.toml"


def default_config_dir():
    """Return the platform-standard per-user configuration directory."""
    if os.name == "nt":
        base = os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        return Path(base) / "CloudFileService"
    if os.uname().sysname == "Darwin":
        return Path.home() / "Library" / "Application Support" / "CloudFileService"
    base = os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")
    return Path(base) / "cloudfs"


def default_config_path():
    return default_config_dir() / DEFAULT_CONFIG_FILE


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
    peers: str = ""


@dataclass(frozen=True)
class ServerConfig:
    host: str = ""
    port: int = 50012
    files_path: str = "files"
    tls_cert_file: str = "certs/server.crt"
    tls_key_file: str = "certs/server.key"
    tls_ca_file: str = "certs/ca.crt"
    registration_enabled: bool = True
    server_id: str = "server1"
    role: str = "primary"
    peers: str = ""
    primary: str = ""
    replication_host: str = ""
    replication_port: int = 60012
    cluster_token: str = ""
    term: int = 1
    replication_timeout: float = 2.0
    heartbeat_interval: float = 0.5
    failure_timeout: float = 2.0
    election_timeout: float = 1.0
    client_addresses: str = ""
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


def _number(value, name: str) -> float:
    if isinstance(value, bool):
        raise ConfigurationError(f"{name} must be a number")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise ConfigurationError(f"{name} must be a number") from error
    if result <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return result


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
    configured = path or os.environ.get("CONFIG_FILE")
    config_path = Path(configured) if configured else default_config_path()
    data = _read_toml(config_path)

    client_port = validate_port(
        _value(data, "client", "port", "CLIENT_PORT", 50012)
    )
    server_port = validate_port(
        _value(data, "server", "port", "SERVER_PORT", 50012)
    )
    replication_port = validate_port(
        _value(
            data,
            "server",
            "replication_port",
            "SERVER_REPLICATION_PORT",
            60012,
        )
    )
    role = str(_value(data, "server", "role", "SERVER_ROLE", "primary"))
    if role not in {"primary", "secondary"}:
        raise ConfigurationError("SERVER_ROLE must be 'primary' or 'secondary'")

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
            peers=str(_value(data, "client", "peers", "CLIENT_PEERS", "")),
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
            server_id=str(
                _value(data, "server", "server_id", "SERVER_ID", "server1")
            ),
            role=role,
            peers=str(_value(data, "server", "peers", "SERVER_PEERS", "")),
            primary=str(
                _value(data, "server", "primary", "SERVER_PRIMARY", "")
            ),
            replication_host=str(
                _value(
                    data,
                    "server",
                    "replication_host",
                    "SERVER_REPLICATION_HOST",
                    "",
                )
            ),
            replication_port=replication_port,
            cluster_token=str(
                _value(data, "server", "cluster_token", "CLUSTER_TOKEN", "")
            ),
            term=_integer(
                _value(data, "server", "term", "SERVER_TERM", 1), "SERVER_TERM"
            ),
            replication_timeout=_number(
                _value(
                    data,
                    "server",
                    "replication_timeout",
                    "REPLICATION_TIMEOUT",
                    2.0,
                ),
                "REPLICATION_TIMEOUT",
            ),
            heartbeat_interval=_number(
                _value(
                    data,
                    "server",
                    "heartbeat_interval",
                    "HEARTBEAT_INTERVAL",
                    0.5,
                ),
                "HEARTBEAT_INTERVAL",
            ),
            failure_timeout=_number(
                _value(
                    data,
                    "server",
                    "failure_timeout",
                    "FAILURE_TIMEOUT",
                    2.0,
                ),
                "FAILURE_TIMEOUT",
            ),
            election_timeout=_number(
                _value(
                    data,
                    "server",
                    "election_timeout",
                    "ELECTION_TIMEOUT",
                    1.0,
                ),
                "ELECTION_TIMEOUT",
            ),
            client_addresses=str(
                _value(
                    data,
                    "server",
                    "client_addresses",
                    "SERVER_CLIENT_ADDRESSES",
                    "",
                )
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

def _toml_value(value):
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"{}"'.format(escaped)


def save_client_config(path, client):
    """Write the client section, preserving any other TOML sections."""
    target = Path(path)
    data = _read_toml(target)
    data["client"] = {
        "server": client.server,
        "port": client.port,
        "local_path": client.local_path,
        "tls_ca_file": client.tls_ca_file,
        "tls_server_name": client.tls_server_name,
        "state_dir": client.state_dir,
        "peers": client.peers,
    }
    lines = []
    for section in sorted(data):
        section_data = data[section]
        if not isinstance(section_data, dict):
            continue
        lines.append("[{}]".format(section))
        for key in sorted(section_data):
            lines.append("{} = {}".format(key, _toml_value(section_data[key])))
        lines.append("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return target
