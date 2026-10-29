import subprocess
import sys

import pytest

from mne_nodes.backend.package_utils import (
    get_import_name,
    install_github_package,
    install_local_plugin,
    install_pip_packages,
)
from mne_nodes.gui.run_widgets import ProcessDialog


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("source", ["pip", "github", "local"])
def test_install_result_after_process_cleanup(
    qtbot, monkeypatch, tmp_path, source, exit_code
):
    """Installation results remain available after Qt deletes the process."""

    def run_test_command(**kwargs):
        kwargs["commands"] = [
            (sys.executable, "-c", f"import sys; sys.exit({exit_code})")
        ]
        kwargs["blocking"] = False
        dialog = ProcessDialog(**kwargs)
        qtbot.addWidget(dialog)
        with qtbot.waitSignal(dialog.process.destroyed, timeout=5000):
            pass
        dialog.close()
        return dialog

    monkeypatch.setattr(
        "mne_nodes.backend.package_utils.ProcessDialog", run_test_command
    )
    if source == "local":
        (tmp_path / "pyproject.toml").write_text("", encoding="utf-8")

    def install():
        if source == "github":
            return install_github_package("https://github.com/owner/plugin")
        if source == "local":
            return install_local_plugin(tmp_path)
        return install_pip_packages(["example-plugin"])

    if exit_code:
        with pytest.raises(
            RuntimeError, match=f"installation failed with exit code {exit_code}"
        ):
            install()
    else:
        dialog = install()
        assert dialog.exit_code == 0


def test_install_and_import_package_at_runtime(tmp_path, qtbot, monkeypatch):
    from mne_nodes.gui.run_widgets import ProcessDialog

    distribution_name = "runtime-import-fixture"
    module_name = "runtime_import_fixture"
    package_path = tmp_path / "package"
    module_path = package_path / module_name
    module_path.mkdir(parents=True)
    (module_path / "__init__.py").write_text("VALUE = 'installed'\n", encoding="utf-8")
    (package_path / "setup.py").write_text(
        "from setuptools import setup\n"
        f"setup(name='{distribution_name}', version='0.0.1', "
        f"packages=['{module_name}'])\n",
        encoding="utf-8",
    )

    def close_dialog_when_finished(**kwargs):
        kwargs["close_directly"] = True
        return ProcessDialog(**kwargs)

    monkeypatch.setattr(
        "mne_nodes.backend.package_utils.ProcessDialog", close_dialog_when_finished
    )

    try:
        install_pip_packages([str(package_path)])
        imported_module_name = get_import_name(distribution_name)
        assert imported_module_name == module_name

        imported_module = __import__(imported_module_name)
        assert imported_module.VALUE == "installed"
    finally:
        subprocess.run(
            [sys.executable, "-m", "pip", "uninstall", "-y", distribution_name],
            check=True,
            capture_output=True,
            text=True,
        )
