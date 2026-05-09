import os

DEFAULT_ZIG_VERSION = "0.16.0"
_ENV_VAR = "ZIGPEEK_VERSION"


def resolve_version(cli_value: str | None) -> str:
    if cli_value is not None:
        if cli_value == "":
            raise ValueError("--version cannot be empty")
        return cli_value
    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        return env_value
    return DEFAULT_ZIG_VERSION
