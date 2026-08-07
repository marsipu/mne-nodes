import importlib
import sys

from qtpy.QtWidgets import QWidget

from mne_nodes.gui.run_widgets import ProcessDialog


def install_pip_packages(package_names: list, parent: QWidget) -> ProcessDialog:
    if len(package_names) == 0:
        raise ValueError("No package names provided for installation.")
    dlg = ProcessDialog(
        parent,
        commands=[(sys.executable, "-m", "pip", "install", *package_names)],
        title=f"Installing Packages {', '.join(package_names)}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg


def uninstall_pip_packages(package_names: list, parent: QWidget) -> ProcessDialog:
    dlg = ProcessDialog(
        parent,
        commands=[(sys.executable, "-m", "pip", "uninstall", "-y", *package_names)],
        title=f"Uninstalling Packages {', '.join(package_names)}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg


def update_pip_packages(package_names: list, parent: QWidget) -> ProcessDialog:
    dlg = ProcessDialog(
        parent,
        commands=[
            (sys.executable, "-m", "pip", "install", "--upgrade", *package_names)
        ],
        title=f"Updating Packages {', '.join(package_names)}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg


def install_github_package(repo_url: str, parent: QWidget) -> ProcessDialog:
    dlg = ProcessDialog(
        parent,
        commands=[(sys.executable, "-m", "pip", "install", f"git+{repo_url}")],
        title=f"Installing GitHub Package {repo_url}",
        blocking=True,
    )

    importlib.invalidate_caches()

    return dlg
