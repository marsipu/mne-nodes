import importlib
import os
import sys
from collections.abc import Iterable
from importlib import import_module, metadata
from importlib.util import cache_from_source, find_spec
from pathlib import Path
from types import ModuleType
from urllib.parse import urlsplit

from packaging.utils import canonicalize_name
from qtpy.QtWidgets import QWidget

from mne_nodes.gui.run_widgets import ProcessDialog


def unload_plugin_modules(
    module_name: str, source_paths: Iterable[Path] = ()
) -> dict[str, ModuleType]:
    """Drop a plugin namespace and its bytecode, returning modules for rollback."""
    previous_modules = {
        name: module
        for name, module in sys.modules.copy().items()
        if (name == module_name or name.startswith(f"{module_name}."))
        and module is not None
    }
    paths = set(source_paths)
    for module in previous_modules.values():
        module_file = getattr(module, "__file__", None)
        if module_file is not None and Path(module_file).suffix == ".py":
            paths.add(Path(module_file))
    for path in paths:
        try:
            os.remove(cache_from_source(str(path)))
        except FileNotFoundError:
            pass
    for name in previous_modules:
        sys.modules.pop(name)
    importlib.invalidate_caches()
    return previous_modules


def get_plugin_entry_points() -> list[metadata.EntryPoint]:
    """List installed plugin registrations without importing plugin code."""
    return sorted(
        metadata.entry_points(group="mne_nodes.plugins"),
        key=lambda entry: (
            entry.dist.name if entry.dist is not None else "",
            entry.name,
            entry.value,
        ),
    )


def find_plugin_entry_point(
    distribution_name: str, entry_point_name: str
) -> metadata.EntryPoint:
    """Resolve a saved registration by distribution and entry-point name."""
    matches = [
        entry
        for entry in get_plugin_entry_points()
        if entry.name == entry_point_name
        and entry.dist is not None
        and canonicalize_name(entry.dist.name) == canonicalize_name(distribution_name)
    ]
    if len(matches) != 1:
        raise LookupError(
            f"Expected one installed plugin entry point '{entry_point_name}' "
            f"in '{distribution_name}', found {len(matches)}. "
            "Install the plugin package or select its new registration."
        )
    return matches[0]


def install_pip_packages(
    package_names: list, parent: QWidget | None = None
) -> ProcessDialog:
    if len(package_names) == 0:
        raise ValueError("No package names provided for installation.")
    dlg = ProcessDialog(
        commands=[(sys.executable, "-m", "pip", "install", *package_names)],
        parent=parent,
        title=f"Installing Packages {', '.join(package_names)}",
        close_directly=False,
        blocking=True,
    )

    importlib.invalidate_caches()
    _raise_on_install_failure(dlg, package_names)

    return dlg


def install_local_plugin(
    project_root: Path, *, editable: bool = True, parent: QWidget | None = None
) -> ProcessDialog:
    """Install a local plugin project, optionally linked to its source."""
    project_root = project_root.resolve()
    if not (project_root / "pyproject.toml").is_file():
        raise ValueError(f"No pyproject.toml found in '{project_root}'.")
    arguments = ["--editable", str(project_root)] if editable else [str(project_root)]
    return install_pip_packages(arguments, parent=parent)


def uninstall_pip_packages(
    package_names: list, parent: QWidget | None = None
) -> ProcessDialog:
    dlg = ProcessDialog(
        commands=[(sys.executable, "-m", "pip", "uninstall", "-y", *package_names)],
        parent=parent,
        title=f"Uninstalling Packages {', '.join(package_names)}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg


def update_pip_packages(
    package_names: list, parent: QWidget | None = None
) -> ProcessDialog:
    dlg = ProcessDialog(
        commands=[
            (sys.executable, "-m", "pip", "install", "--upgrade", *package_names)
        ],
        parent=parent,
        title=f"Updating Packages {', '.join(package_names)}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg


def install_github_package(
    repo_url: str, parent: QWidget | None = None
) -> ProcessDialog:
    repo_url = normalize_github_url(repo_url)
    dlg = ProcessDialog(
        commands=[(sys.executable, "-m", "pip", "install", f"git+{repo_url}")],
        parent=parent,
        title=f"Installing GitHub Package {repo_url}",
        close_directly=False,
        blocking=True,
    )

    importlib.invalidate_caches()
    _raise_on_install_failure(dlg, [repo_url])

    return dlg


def _raise_on_install_failure(dialog: ProcessDialog, packages: list[str]) -> None:
    """Raise an error when a pip process did not complete successfully."""
    package_list = ", ".join(packages)
    if dialog.exit_code is None:
        raise RuntimeError(f"Package installation did not complete: {package_list}")
    if dialog.exit_code != 0:
        raise RuntimeError(
            f"Package installation failed with exit code "
            f"{dialog.exit_code}: {package_list}"
        )


def get_import_name(distribution_name: str) -> str:
    """Return the importable top-level module for an installed distribution."""
    registered_modules = {
        entry.module
        for entry in get_plugin_entry_points()
        if entry.dist is not None
        and canonicalize_name(entry.dist.name) == canonicalize_name(distribution_name)
    }
    if len(registered_modules) == 1:
        return registered_modules.pop()
    if registered_modules:
        raise ImportError(
            f"Distribution '{distribution_name}' registers multiple plugins. "
            "Select one using Load Installed Plugin."
        )
    normalized_name = distribution_name.replace("-", "_").lower()
    distribution_map = metadata.packages_distributions()
    candidates = [
        module_name
        for module_name, distributions in distribution_map.items()
        if any(
            distribution.replace("-", "_").lower() == normalized_name
            for distribution in distributions
        )
    ]
    importlib.invalidate_caches()
    importable_candidates = [
        candidate for candidate in candidates if find_spec(candidate)
    ]
    if len(importable_candidates) == 1:
        return importable_candidates[0]
    if len(importable_candidates) > 1:
        raise ImportError(
            f"Distribution '{distribution_name}' exposes multiple import modules: "
            f"{', '.join(sorted(importable_candidates))}."
        )

    if find_spec(normalized_name) is not None:
        return normalized_name
    raise ModuleNotFoundError(
        f"Could not find an importable module for distribution '{distribution_name}'."
    )


def import_distribution(distribution_name: str) -> ModuleType:
    """Import the module of an installed distribution, by distribution name."""
    return import_module(get_import_name(distribution_name))


def normalize_github_url(url: str) -> str:
    """Normalize and validate a GitHub repository URL."""
    if not isinstance(url, str):
        raise TypeError("GitHub URL must be a string.")

    normalized_url = url.strip().replace("\\", "/")
    parts = urlsplit(normalized_url)
    hostname = (parts.hostname or "").lower()
    path_parts = [part for part in parts.path.split("/") if part]

    if parts.scheme not in {"http", "https"} or hostname not in {
        "github.com",
        "www.github.com",
    }:
        raise ValueError("URL must point to a GitHub repository.")
    if len(path_parts) != 2:
        raise ValueError(
            "Expected a GitHub repository URL such as "
            "'https://github.com/owner/repository'."
        )

    owner, repository = path_parts
    repository = repository.removesuffix(".git")
    if not owner or not repository:
        raise ValueError("GitHub URL must include an owner and repository name.")

    return f"https://github.com/{owner}/{repository}"


def get_name_from_github(url: str) -> str:
    """Return the repository name from a GitHub repository URL."""
    normalized_url = normalize_github_url(url)
    return urlsplit(normalized_url).path.rsplit("/", maxsplit=1)[-1]
