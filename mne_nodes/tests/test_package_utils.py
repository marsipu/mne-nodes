import subprocess
import sys

from mne_nodes.pipeline.package_utils import get_import_name, install_pip_packages


def test_install_and_import_package_at_runtime(tmp_path, qtbot):
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
