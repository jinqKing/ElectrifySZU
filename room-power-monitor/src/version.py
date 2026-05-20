from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
import tomllib

PROJECT_NAME = "electrifyszu"


def project_version() -> str:
    """Read the project version from package metadata or the source tree."""
    try:
        return version(PROJECT_NAME)
    except PackageNotFoundError:
        pass

    for parent in Path(__file__).resolve().parents:
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file():
            with pyproject.open("rb") as f:
                return str(tomllib.load(f)["project"]["version"])
    raise RuntimeError("Unable to locate pyproject.toml")


__version__ = project_version()
