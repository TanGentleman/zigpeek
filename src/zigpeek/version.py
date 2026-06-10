import os

# "master" tracks the 0.17-dev docs on ziglang.org; switch to "0.17.0"
# once that release ships.
DEFAULT_ZIG_VERSION = "master"
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
