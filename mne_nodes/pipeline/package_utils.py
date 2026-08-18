import importlib
import sys
from importlib import import_module, metadata
from importlib.util import find_spec
from types import ModuleType
from urllib.parse import urlsplit

from qtpy.QtWidgets import QWidget

from mne_nodes.gui.run_widgets import ProcessDialog


def install_pip_packages(
    package_names: list, parent: QWidget | None = None
) -> ProcessDialog:
    if len(package_names) == 0:
        raise ValueError("No package names provided for installation.")
    dlg = ProcessDialog(
        commands=[(sys.executable, "-m", "pip", "install", *package_names)],
        parent=parent,
        title=f"Installing Packages {', '.join(package_names)}",
        close_directly=True,
        blocking=True,
    )

    importlib.invalidate_caches()
    _raise_on_install_failure(dlg, package_names)

    return dlg


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
        close_directly=True,
        blocking=True,
    )

    importlib.invalidate_caches()
    _raise_on_install_failure(dlg, [repo_url])

    return dlg


def _raise_on_install_failure(dialog: ProcessDialog, packages: list[str]) -> None:
    """Raise an error when a pip process did not complete successfully."""
    if dialog.process.exitCode() != 0:
        package_list = ", ".join(packages)
        raise RuntimeError(
            f"Package installation failed with exit code "
            f"{dialog.process.exitCode()}: {package_list}"
        )


def get_import_name(distribution_name: str) -> str:
    """Return the importable top-level module for an installed distribution."""
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
