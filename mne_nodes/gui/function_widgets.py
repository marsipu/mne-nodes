"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import inspect
import os
import shutil
from ast import literal_eval
from importlib import util
from os import mkdir
from os.path import isdir, isfile, join
from types import FunctionType
from typing import List

import pandas as pd
from qtpy.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from mne_nodes.gui import parameter_widgets
from mne_nodes.gui.base_widgets import CheckList, EditDict, EditList, SimpleList
from mne_nodes.gui.dialogs import ErrorDialog
from mne_nodes.pipeline.exception_handling import get_exception_tuple
from mne_nodes.qt_compat import CHECKED, UNCHECKED, ITEM_IS_USER_CHECKABLE


class EditGuiArgsDlg(QDialog):
    def __init__(self, cf_dialog) -> None:
        super().__init__(cf_dialog)
        self.cf = cf_dialog
        self.gui_args = {}
        self.default_gui_args = {}

        if self.cf.current_parameter:
            covered_params = [
                "data",
                "name",
                "alias",
                "default",
                "unit",
                "none_select",
                "description",
            ]
            # Get possible default GUI-Args additional to those
            # covered by the Main-GUI
            gui_type = self.cf.add_pd_params.loc[self.cf.current_parameter, "gui_type"]
            if pd.notna(gui_type):
                gui_handle = getattr(parameter_widgets, gui_type)
                psig = inspect.signature(gui_handle).parameters
                self.default_gui_args = {
                    p: psig[p].default for p in psig if p not in covered_params
                }

            # Get current GUI-Args
            loaded_gui_args = self.cf.add_pd_params.loc[
                self.cf.current_parameter, "gui_args"
            ]
            if pd.notna(loaded_gui_args):
                self.gui_args = literal_eval(loaded_gui_args)
            else:
                self.gui_args = {}

            # Fill in all possible Options, which are not already changed
            for arg_key in [
                ak for ak in self.default_gui_args if ak not in self.gui_args
            ]:
                self.gui_args[arg_key] = self.default_gui_args[arg_key]

            if len(self.gui_args) > 0:
                self.init_ui()
                self.open()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(EditDict(data=self.gui_args, ui_buttons=False))

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)

    def closeEvent(self, event):
        # Remove all options which don't differ from the default
        for arg_key in [
            ak for ak in self.gui_args if self.gui_args[ak] == self.default_gui_args[ak]
        ]:
            self.gui_args.pop(arg_key)

        if len(self.gui_args) > 0:
            self.cf.pguiargs_changed(self.gui_args)

        event.accept()


class ChooseOptions(QDialog):
    def __init__(self, cf_dialog, gui_type: str, options: List[str]) -> None:
        super().__init__(cf_dialog)
        self.cf = cf_dialog
        self.gui_type = gui_type
        self.options = options

        self.init_ui()
        # If open(), execution doesn't stop after the dialog
        self.exec()

    def init_ui(self):
        layout = QVBoxLayout()
        layout.addWidget(
            QLabel(
                f"For {self.gui_type}, you need to specify the options to choose from"
            )
        )
        layout.addWidget(EditList(data=self.options))
        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)
        self.setLayout(layout)


# ToDo:
#   Bug1: After saving a new function, the parameters stay in the table-view,
#   Bug2: When editing existing functions, the proprietary
#   parameters can not be edited (they land in exising_params)
#   Bug3: When hitting Enter, the focus still lies on the
#   AddFunc/EditFunc-Buttons which can disrupt setup
# ToDo:
#   Feature1: Code Display in middle with color highlighting
#   and color coding the parameters etc.
#   Feature2: Restrict parameter names to make sure they aren't similar
#   to data-types or something like ct/controller/pr


class ImportFuncs(QDialog):
    def __init__(self, cf_dialog, edit_existing: bool = False) -> None:
        super().__init__(cf_dialog)
        self.cf = cf_dialog
        self.edit_existing = edit_existing

        self.module = None
        self.loaded_cfs = []
        self.edit_loaded_cfs = []
        self.selected_cfs = []
        self.selected_edit_cfs = []
        self.already_existing_funcs = []

        self.load_function_list()
        self.init_ui()

        self.open()

    def load_function_list(self):
        # Load .csv-Files if
        try:
            if self.edit_existing:
                self.cf.pkg_name = self.cf.file_path.parent.name
                pd_funcs_path = join(
                    self.cf.file_path.parent, f"{self.cf.pkg_name}_functions.csv"
                )
                pd_params_path = join(
                    self.cf.file_path.parent, f"{self.cf.pkg_name}_parameters.csv"
                )
                self.cf.add_pd_funcs = pd.read_csv(
                    pd_funcs_path,
                    sep=";",
                    index_col=0,
                    na_values=[""],
                    keep_default_na=False,
                )
                self.cf.add_pd_params = pd.read_csv(
                    pd_params_path,
                    sep=";",
                    index_col=0,
                    na_values=[""],
                    keep_default_na=False,
                )

                # Can be removed soon, when nobody uses
                # old packages anymore (10.11.2020)
                if "target" not in self.cf.add_pd_funcs.columns:
                    self.cf.add_pd_funcs["target"] = None
            else:
                self.cf.pkg_name = None
            spec = util.spec_from_file_location(
                self.cf.file_path.stem, self.cf.file_path
            )
            self.module = util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        except Exception:
            err = get_exception_tuple()
            ErrorDialog(err, self)
        else:
            for func_key in self.module.__dict__:
                func = self.module.__dict__[func_key]
                # Only functions are allowed
                # (Classes should be called from function!)
                if (
                    isinstance(func, FunctionType)
                    and func.__module__ == self.module.__name__
                ):
                    # Check, if function is already existing
                    if func_key in self.cf.exst_functions:
                        if (
                            self.edit_existing
                            and func_key in self.cf.add_pd_funcs.index
                        ):
                            self.edit_loaded_cfs.append(func_key)
                        else:
                            self.already_existing_funcs.append(func_key)
                    else:
                        self.loaded_cfs.append(func_key)

    def init_ui(self):
        layout = QVBoxLayout()

        if len(self.already_existing_funcs) > 0:
            exst_label = QLabel(
                f"These functions already exist: {self.already_existing_funcs}"
            )
            exst_label.setWordWrap(True)
            layout.addWidget(exst_label)

        view_layout = QHBoxLayout()
        load_list = CheckList(
            self.loaded_cfs,
            self.selected_cfs,
            ui_button_pos="bottom",
            title="New functions",
        )
        view_layout.addWidget(load_list)

        if len(self.edit_loaded_cfs) > 0:
            edit_list = CheckList(
                self.edit_loaded_cfs,
                self.selected_edit_cfs,
                ui_button_pos="bottom",
                title="Functions to edit",
            )
            view_layout.addWidget(edit_list)

        layout.addLayout(view_layout)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setWindowTitle("Choose Functions")
        self.setLayout(layout)

    def load_selected_functions(self):
        selected_funcs = [cf for cf in self.loaded_cfs if cf in self.selected_cfs] + [
            cf for cf in self.edit_loaded_cfs if cf in self.selected_edit_cfs
        ]
        if self.edit_existing:
            # Drop Functions which are not selected
            self.cf.add_pd_funcs.drop(
                index=[
                    f for f in self.cf.add_pd_funcs.index if f not in selected_funcs
                ],
                inplace=True,
            )

        for func_key in selected_funcs:
            func = self.module.__dict__[func_key]

            self.cf.add_pd_funcs.loc[func_key, "module"] = self.module.__name__
            self.cf.add_pd_funcs.loc[func_key, "ready"] = 0

            self.cf.code_dict[func_key] = inspect.getsource(func)

            # Get Parameters and divide them in existing and setup
            all_parameters = list(inspect.signature(func).parameters)
            self.cf.add_pd_funcs.loc[func_key, "func_args"] = ",".join(all_parameters)
            existing_parameters = []

            for param_key in all_parameters:
                if param_key in self.cf.exst_parameters:
                    existing_parameters.append(param_key)
                else:
                    # Check if ready (possible when editing functions)
                    self.cf.add_pd_params.loc[param_key, "ready"] = 0
                    if pd.notna(
                        self.cf.add_pd_params.loc[param_key, self.cf.oblig_params]
                    ).all():
                        self.cf.add_pd_params.loc[param_key, "ready"] = 1

                    # functions (which are using param) is a continuous string
                    # (because pandas can't store a list as item)
                    if param_key in self.cf.add_pd_params.index:
                        if "functions" in self.cf.add_pd_params.columns:
                            if pd.notna(
                                self.cf.add_pd_params.loc[param_key, "functions"]
                            ):
                                self.cf.add_pd_params.loc[param_key, "functions"] += (
                                    func_key
                                )
                            else:
                                self.cf.add_pd_params.loc[param_key, "functions"] = (
                                    func_key
                                )
                        else:
                            self.cf.add_pd_params.loc[param_key, "functions"] = func_key
                    else:
                        self.cf.add_pd_params.loc[param_key, "functions"] = func_key

            self.cf.param_exst_dict[func_key] = existing_parameters

        # Check, if mandatory columns exist
        if "ready" not in self.cf.add_pd_params.columns:
            self.cf.add_pd_params["ready"] = 0
        if "functions" not in self.cf.add_pd_params.columns:
            self.cf.add_pd_params["functions"] = ""

    def closeEvent(self, event):
        self.load_selected_functions()
        self.cf.update_func_cmbx()
        self.cf.update_exst_param_label()
        if self.cf.code_editor:
            self.cf.code_editor.update_code()
        event.accept()


class SelectDependencies(QDialog):
    def __init__(self, cf_dialog):
        super().__init__(cf_dialog)
        self.cf_dialog = cf_dialog
        if pd.notna(
            cf_dialog.add_pd_funcs.loc[cf_dialog.current_function, "dependencies"]
        ):
            self.dpd_list = literal_eval(
                cf_dialog.add_pd_funcs.loc[cf_dialog.current_function, "dependencies"]
            )
        else:
            self.dpd_list = []

        layout = QVBoxLayout()
        self.listw = QListWidget()
        self.listw.itemChanged.connect(self.item_checked)
        layout.addWidget(self.listw)

        ok_bt = QPushButton("OK")
        ok_bt.clicked.connect(self.close_dlg)
        layout.addWidget(ok_bt)

        self.populate_listw()
        self.setLayout(layout)
        self.open()

    def populate_listw(self):
        for function in self.cf_dialog.ct.pd_funcs.index:
            item = QListWidgetItem(function)
            item.setFlags(item.flags() | ITEM_IS_USER_CHECKABLE)
            if function in self.dpd_list:
                item.setCheckState(CHECKED)
            else:
                item.setCheckState(UNCHECKED)
            self.listw.addItem(item)

    def item_checked(self, item):
        if item.checkState == CHECKED:
            self.dpd_list.append(item.text())
        elif item.text() in self.dpd_list:
            self.dpd_list.remove(item.text())

    def close_dlg(self):
        self.cf_dialog.add_pd_funcs.loc[
            self.cf_dialog.current_function, "dependencies"
        ] = str(self.dpd_list)
        self.close()


class TestParamGui(QDialog):
    def __init__(self, cf_dialog):
        super().__init__(cf_dialog)
        self.cf = cf_dialog
        # Dict as Replacement for Parameters in Project for Testing
        self.test_parameters = {}

        default_string = self.cf.add_pd_params.loc[self.cf.current_parameter, "default"]
        gui_type = self.cf.add_pd_params.loc[self.cf.current_parameter, "gui_type"]
        try:
            gui_args = literal_eval(
                self.cf.add_pd_params.loc[self.cf.current_parameter, "gui_args"]
            )
        except (SyntaxError, ValueError):
            gui_args = {}

        self.result, self.gui = self.cf.test_param_gui(
            default_string, gui_type, gui_args
        )

        if not self.result:
            self.init_ui()
            self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        # Allow Enter-Press without closing the dialog
        if (
            self.cf.add_pd_params.loc[self.cf.current_parameter, "gui_type"]
            == "FuncGui"
        ):
            void_bt = QPushButton()
            void_bt.setDefault(True)
            layout.addWidget(void_bt)

        layout.addWidget(self.gui)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)
        self.setLayout(layout)


class SavePkgDialog(QDialog):
    def __init__(self, cf_dialog):
        super().__init__(cf_dialog)
        self.cf_dialog = cf_dialog

        self.my_pkg_name = None
        self.pkg_path = None

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        self.func_list = SimpleList(
            list(
                self.cf_dialog.add_pd_funcs.loc[
                    self.cf_dialog.add_pd_funcs["ready"] == 1
                ].index
            )
        )
        layout.addWidget(self.func_list)

        pkg_name_label = QLabel("Package-Name:")
        layout.addWidget(pkg_name_label)

        self.pkg_le = QLineEdit()
        if self.cf_dialog.pkg_name:
            self.pkg_le.setText(self.cf_dialog.pkg_name)
        self.pkg_le.textEdited.connect(self.pkg_le_changed)
        layout.addWidget(self.pkg_le)

        save_bt = QPushButton("Save")
        save_bt.clicked.connect(self.save_pkg)
        layout.addWidget(save_bt)

        cancel_bt = QPushButton("Cancel")
        cancel_bt.clicked.connect(self.close)
        layout.addWidget(cancel_bt)
        self.setLayout(layout)

    def pkg_le_changed(self, text):
        if text != "":
            self.my_pkg_name = text

    def save_pkg(self):
        if self.my_pkg_name or self.cf_dialog.pkg_name:
            # Drop all functions with unfinished setup
            # and add the remaining to the main_window-DataFrame
            drop_funcs = self.cf_dialog.add_pd_funcs.loc[
                self.cf_dialog.add_pd_funcs["ready"] == 0
            ].index
            final_add_pd_funcs = self.cf_dialog.add_pd_funcs.drop(index=drop_funcs)

            drop_params = []
            for param in self.cf_dialog.add_pd_params.index:
                if not any(
                    [
                        f in str(self.cf_dialog.add_pd_params.loc[param, "functions"])
                        for f in final_add_pd_funcs.index
                    ]
                ):
                    drop_params.append(param)
            final_add_pd_params = self.cf_dialog.add_pd_params.drop(index=drop_params)

            # Remove no longer needed columns
            del final_add_pd_funcs["ready"]
            del final_add_pd_params["ready"]
            del final_add_pd_params["functions"]

            # Todo: Make this more failproof
            #  (loading and saving already existing packages)
            # This is only not None, when the function
            # was imported by edit-functions
            if self.cf_dialog.pkg_name:
                # Update and overwrite existing settings for funcs and params
                self.pkg_path = join(
                    self.cf_dialog.ct.custom_pkg_path, self.cf_dialog.pkg_name
                )
                pd_funcs_path = join(
                    self.pkg_path, f"{self.cf_dialog.pkg_name}_functions.csv"
                )
                pd_params_path = join(
                    self.pkg_path, f"{self.cf_dialog.pkg_name}_parameters.csv"
                )
                if isfile(pd_funcs_path):
                    read_pd_funcs = pd.read_csv(
                        pd_funcs_path,
                        sep=";",
                        index_col=0,
                        na_values=[""],
                        keep_default_na=False,
                    )
                    # Replace indexes from file with same name
                    drop_funcs = [
                        f for f in read_pd_funcs.index if f in final_add_pd_funcs.index
                    ]
                    read_pd_funcs.drop(index=drop_funcs, inplace=True)
                    final_add_pd_funcs = pd.concat([read_pd_funcs, final_add_pd_funcs])
                if isfile(pd_params_path):
                    read_pd_params = pd.read_csv(
                        pd_params_path,
                        sep=";",
                        index_col=0,
                        na_values=[""],
                        keep_default_na=False,
                    )
                    # Replace indexes from file with same name
                    drop_params = [
                        p
                        for p in read_pd_params.index
                        if p in final_add_pd_params.index
                    ]
                    read_pd_params.drop(index=drop_params, inplace=True)
                    final_add_pd_params = pd.concat(
                        [read_pd_params, final_add_pd_params]
                    )

                if self.my_pkg_name and self.my_pkg_name != self.cf_dialog.pkg_name:
                    # Rename folder and .csv-files if you enter a new name
                    new_pkg_path = join(
                        self.cf_dialog.ct.custom_pkg_path, self.my_pkg_name
                    )
                    os.rename(self.pkg_path, new_pkg_path)

                    new_pd_funcs_path = join(
                        new_pkg_path, f"{self.my_pkg_name}_functions.csv"
                    )
                    os.rename(pd_funcs_path, new_pd_funcs_path)
                    pd_funcs_path = new_pd_funcs_path

                    new_pd_params_path = join(
                        new_pkg_path, f"{self.my_pkg_name}_parameters.csv"
                    )
                    os.rename(pd_params_path, new_pd_params_path)
                    pd_params_path = new_pd_params_path

            else:
                self.pkg_path = join(
                    self.cf_dialog.ct.custom_pkg_path, self.my_pkg_name
                )
                if not isdir(self.pkg_path):
                    mkdir(self.pkg_path)
                # Create __init__.py to make it a package
                with open(join(self.pkg_path, "__init__.py"), "w") as f:
                    f.write("")
                # Copy Origin-Script to Destination
                pd_funcs_path = join(self.pkg_path, f"{self.my_pkg_name}_functions.csv")
                pd_params_path = join(
                    self.pkg_path, f"{self.my_pkg_name}_parameters.csv"
                )
                dest_path = join(self.pkg_path, self.cf_dialog.file_path.name)
                shutil.copy2(self.cf_dialog.file_path, dest_path)

            # Add pkg_name as column if not already existing
            if "pkg_name" in final_add_pd_funcs:
                final_add_pd_funcs["pkg_name"] = self.my_pkg_name
            else:
                final_add_pd_funcs.insert(
                    len(final_add_pd_funcs.columns) - 1, "pkg_name", self.my_pkg_name
                )

            final_add_pd_funcs.to_csv(pd_funcs_path, sep=";")
            final_add_pd_params.to_csv(pd_params_path, sep=";")

            for func in [
                f
                for f in final_add_pd_funcs.index
                if f in self.cf_dialog.add_pd_funcs.index
            ]:
                self.cf_dialog.add_pd_funcs.drop(index=func, inplace=True)
            self.cf_dialog.update_func_cmbx()
            for param in [
                p
                for p in final_add_pd_params.index
                if p in self.cf_dialog.add_pd_params
            ]:
                self.cf_dialog.add_pd_params.drop(index=param, inplace=True)
            self.cf_dialog.clear_func_items()
            self.cf_dialog.clear_param_items()

            # Add to selected modules
            self.cf_dialog.ct.settings.get("selected_modules").append(
                self.cf_dialog.file_path.stem
            )
            self.cf_dialog.ct.save_settings()

            self.cf_dialog.ct.import_custom_modules()
            self.cf_dialog.mw.redraw_func_and_param()
            # ToDo: MP
            # init_mp_pool()
            self.close()

        else:
            # If no valid pkg_name is existing
            QMessageBox.warning(
                self,
                "No valid Package-Name!",
                "You need to enter a valid Package-Name!",
            )
