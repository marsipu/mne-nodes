"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

from .base import Base, BaseList
from .dict_widgets import BaseDict, EditDict, SimpleDict
from .list_widgets import (
    CheckDictEditList,
    CheckDictList,
    CheckList,
    CheckListProgress,
    EditList,
    ProgressDelegate,
    SimpleList,
)
from .misc_widgets import AssignWidget, ComboBox, SimpleDialog, TimedMessageBox
from .pandas_widgets import BasePandasTable, EditPandasTable, SimplePandasTable
from .tree_widgets import ShallowTreeWidget, TreeWidget

__all__ = [
    "AssignWidget",
    "Base",
    "BaseDict",
    "BaseList",
    "BasePandasTable",
    "CheckDictEditList",
    "CheckDictList",
    "CheckList",
    "CheckListProgress",
    "ComboBox",
    "EditDict",
    "EditList",
    "EditPandasTable",
    "ProgressDelegate",
    "ShallowTreeWidget",
    "SimpleDialog",
    "SimpleDict",
    "SimpleList",
    "SimplePandasTable",
    "TimedMessageBox",
    "TreeWidget",
]
