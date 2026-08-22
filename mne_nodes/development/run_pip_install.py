import sys

from qtpy.QtWidgets import QApplication

from mne_nodes.pipeline.package_utils import (
    install_github_package,
    install_pip_packages,
)

app = QApplication(sys.argv)
install_pip_packages(["numpy", "scipy"], parent=None)

install_github_package("https://github.com/marsipu/mne-nodes", parent=None)
