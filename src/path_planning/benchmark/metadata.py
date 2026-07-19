"""Execution-environment metadata for reproducible benchmark runs."""

import hashlib
import importlib.metadata
import json
import platform
import re
import subprocess
import tomllib
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from path_planning.core.types import JsonValue

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SOURCE_PATTERNS = (
    "src/path_planning/**/*.py",
    "configs/**/*.yaml",
    "maps/**/*.json",
    "pyproject.toml",
    "requirements.lock",
)


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def collect_run_metadata(
    config_bytes: bytes,
    config_path: Path,
) -> dict[str, JsonValue]:
    """Capture traceability and the dependency versions in this environment."""
    lock_bytes = (_PROJECT_ROOT / "requirements.lock").read_bytes()
    snapshot_overrides = {"requirements.lock": lock_bytes}
    try:
        relative_config = config_path.resolve().relative_to(_PROJECT_ROOT.resolve())
    except ValueError:
        pass
    else:
        snapshot_overrides[relative_config.as_posix()] = config_bytes
    return {
        "schema_version": 1,
        "run_id": uuid.uuid4().hex,
        "config_sha256": sha256_bytes(config_bytes),
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "direct_dependencies": _direct_dependencies(),
        "resolved_dependencies": _resolved_dependencies(lock_bytes),
        "requirements_lock_sha256": sha256_bytes(lock_bytes),
        "source_snapshot": _source_snapshot(snapshot_overrides),
        "executed_at_utc": datetime.now(UTC).isoformat(),
    }


def _git_commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _git_dirty() -> bool:
    return bool(
        subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=_PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )


def _direct_dependencies() -> dict[str, JsonValue]:
    root = _mapping(
        tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")),
        "pyproject",
    )
    project = _mapping(root.get("project"), "project")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(dependency, str) for dependency in dependencies
    ):
        raise ValueError("project dependencies must be a list of strings")
    names = sorted(_dependency_name(dependency) for dependency in dependencies)
    return {name: _installed_version(name) for name in names}


def _resolved_dependencies(lock_bytes: bytes) -> dict[str, JsonValue]:
    dependencies: dict[str, JsonValue] = {}
    for line in lock_bytes.decode("utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        name, separator, locked_version = line.partition("==")
        if not separator or not name:
            raise ValueError("requirements.lock entries must pin exact versions")
        normalized_name = _normalize_name(name)
        installed_version = _installed_version(normalized_name)
        if installed_version != locked_version:
            raise RuntimeError(
                "dependency version mismatch for "
                f"{normalized_name}: locked {locked_version}, "
                f"installed {installed_version}"
            )
        dependencies[normalized_name] = {
            "locked": locked_version,
            "installed": installed_version,
        }
    return dependencies


def _source_snapshot(overrides: Mapping[str, bytes]) -> dict[str, JsonValue]:
    paths = {
        path
        for pattern in _SOURCE_PATTERNS
        for path in _PROJECT_ROOT.glob(pattern)
        if path.is_file()
    }
    file_hashes: dict[str, JsonValue] = {}
    for path in sorted(paths):
        relative = path.relative_to(_PROJECT_ROOT).as_posix()
        content = overrides[relative] if relative in overrides else path.read_bytes()
        file_hashes[relative] = sha256_bytes(content)
    canonical = json.dumps(
        file_hashes,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {"files": file_hashes, "sha256": sha256_bytes(canonical)}


def _installed_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError as error:
        raise RuntimeError(f"dependency is not installed: {name}") from error


def _dependency_name(requirement: str) -> str:
    match = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", requirement)
    if match is None:
        raise ValueError(f"invalid project dependency: {requirement}")
    return _normalize_name(match.group())


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _mapping(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{field} must be a string-keyed mapping")
    return cast(dict[str, object], value)
