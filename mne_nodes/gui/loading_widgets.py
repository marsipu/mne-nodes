"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import logging
import os
import shutil
import time
from functools import partial
from os.path import isfile, join
from pathlib import Path
from typing import Optional, Callable

import mne
import numpy as np
from matplotlib import pyplot as plt
from qtpy import compat
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.base_widgets import (
    AssignWidget,
    CheckDictList,
    CheckList,
    EditDict,
    SimpleList,
)
from mne_nodes.gui.gui_utils import set_ratio_geometry, warning_message
from mne_nodes.gui.parameter_widgets import ComboGui
from mne_nodes.pipeline.exception_handling import gui_error
from mne_nodes.pipeline.execution import WorkerDialog
from mne_nodes.pipeline.pipeline_utils import get_n_jobs
from mne_nodes.pipeline.settings import Settings

MEEG = None


def find_bads(meeg, n_jobs, **kwargs):
    raw = meeg.load_raw()

    if raw.info["dev_head_t"] is None:
        coord_frame = "meg"
    else:
        coord_frame = "head"

    # Set number of CPU-cores to use
    os.environ["OMP_NUM_THREADS"] = str(get_n_jobs(n_jobs))

    noisy_chs, flat_chs = mne.preprocessing.find_bad_channels_maxwell(
        raw, coord_frame=coord_frame, **kwargs
    )
    logging.info(f"Noisy channels: {noisy_chs}\nFlat channels: {flat_chs}")
    raw.info["bads"] = noisy_chs + flat_chs + raw.info["bads"]
    meeg.set_bad_channels(raw.info["bads"])
    meeg.save_raw(raw)


def _save_ica_on_close(_, meeg, ica):
    meeg.set_ica_exclude(ica.exclude)
    meeg.save_ica(ica)


def plot_ica_components(meeg, show_plots, close_func=_save_ica_on_close):
    ica = meeg.load_ica()
    figs = ica.plot_components(title=meeg.name, show=show_plots)
    if not isinstance(figs, list):
        figs = [figs]
    figs[0].canvas.mpl_connect("close_event", partial(close_func, meeg=meeg, ica=ica))
    meeg.plot_save("ica", subfolder="components", matplotlib_figure=figs)


def plot_ica_sources(meeg, ica_source_data, show_plots, close_func=_save_ica_on_close):
    ica = meeg.load_ica()
    data = meeg.load(ica_source_data)

    fig = ica.plot_sources(data, title=meeg.name, show=show_plots)
    if hasattr(fig, "canvas"):
        # Connect to closing of Matplotlib-Figure
        fig.canvas.mpl_connect("close_event", partial(close_func, meeg=meeg, ica=ica))
        # Save plot as image
        meeg.plot_save("ica", subfolder="sources", matplotlib_figure=fig)
    else:
        # Connect to closing of PyQt-Figure
        fig.gotClosed.connect(partial(close_func, None, meeg=meeg, ica=ica))


def plot_ica_overlay(meeg, ica_overlay_data, show_plots):
    ica = meeg.load_ica()
    data = meeg.load(ica_overlay_data)

    overlay_figs = []

    if ica_overlay_data == "evoked":
        for evoked in [e for e in data if e.comment in meeg.sel_trials]:
            ovl_fig = ica.plot_overlay(
                evoked, title=f"{meeg.name}-{evoked.comment}", show=show_plots
            )
            overlay_figs.append(ovl_fig)
    else:
        ovl_fig = ica.plot_overlay(data, title=meeg.name, show=show_plots)
        overlay_figs.append(ovl_fig)

    meeg.plot_save("ica", subfolder="overlay", matplotlib_figure=overlay_figs)

    return overlay_figs


def plot_ica_properties(meeg, ica_fitto, show_plots):
    ica = meeg.load_ica()

    eog_indices = meeg.load_json("eog_indices", default=list())
    ecg_indices = meeg.load_json("ecg_indices", default=list())
    psd_args = {"fmax": meeg.pa["lowpass"]}

    if len(eog_indices) > 0:
        eog_epochs = meeg.load_eog_epochs()
        eog_prop_figs = ica.plot_properties(
            eog_epochs, eog_indices, psd_args=psd_args, show=show_plots
        )
        meeg.plot_save(
            "ica", subfolder="properties", trial="eog", matplotlib_figure=eog_prop_figs
        )

    if len(ecg_indices) > 0:
        ecg_epochs = meeg.load_ecg_epochs()
        ecg_prop_figs = ica.plot_properties(
            ecg_epochs, ecg_indices, psd_args=psd_args, show=show_plots
        )
        meeg.plot_save(
            "ica", subfolder="properties", trial="ecg", matplotlib_figure=ecg_prop_figs
        )

    remaining_indices = [
        ix for ix in ica.exclude if ix not in eog_indices + ecg_indices
    ]
    if len(remaining_indices) > 0:
        data = meeg.load(ica_fitto)
        prop_figs = ica.plot_properties(
            data, remaining_indices, psd_args=psd_args, show=show_plots
        )
        meeg.plot_save(
            "ica", subfolder="properties", trial="manually", matplotlib_figure=prop_figs
        )


def _save_raw_on_close(_, meeg: "MEEG", raw, raw_type: str) -> None:
    # Save bad-channels
    meeg.set_bad_channels(raw.info["bads"])
    # Save raw for annotations
    meeg.save(raw_type, raw)


def plot_raw(
    meeg: "MEEG",
    show_plots: bool,
    close_func: Optional[Callable] = _save_raw_on_close,
    **kwargs,
) -> None:
    raw = meeg.load_raw()

    try:
        events = meeg.load_events()
    except FileNotFoundError:
        events = None
        print("No events found")

    fig = raw.plot(
        events=events,
        bad_color="red",
        scalings="auto",
        title=f"{meeg.name}",
        show=show_plots,
        **kwargs,
    )

    if hasattr(fig, "canvas"):
        # Connect to closing of Matplotlib-Figure
        fig.canvas.mpl_connect(
            "close_event", partial(close_func, meeg=meeg, raw=raw, raw_type="raw")
        )
    else:
        # Connect to closing of PyQt-Figure
        fig.gotClosed.connect(
            partial(close_func, None, meeg=meeg, raw=raw, raw_type="raw")
        )


def index_parser(index, all_items, groups=None):
    """Parses indices from a index-string in all_items.

    Parameters
    ----------
    index: str
        A string which contains information about indices
    all_items
        All items
    Returns
    -------
    """
    indices = []
    rm = []

    try:
        if index == "":
            return [], []
        elif "all" in index:
            if "," in index:
                splits = index.split(",")
                for sp in splits:
                    if "!" in sp and "-" in sp:
                        x, y = sp.split("-")
                        x = x[1:]
                        for n in range(int(x), int(y) + 1):
                            rm.append(n)
                    elif "!" in sp:
                        rm.append(int(sp[1:]))
                    elif "all" in sp:
                        for i in range(len(all_items)):
                            indices.append(i)
            else:
                indices = [x for x in range(len(all_items))]

        elif "," in index and "-" in index:
            z = index.split(",")
            for i in z:
                if "-" in i and "!" not in i:
                    x, y = i.split("-")
                    for n in range(int(x), int(y) + 1):
                        indices.append(n)
                elif "!" not in i:
                    indices.append(int(i))
                elif "!" in i and "-" in i:
                    x, y = i.split("-")
                    x = x[1:]
                    for n in range(int(x), int(y) + 1):
                        rm.append(n)
                elif "!" in i:
                    rm.append(int(i[1:]))

        elif "-" in index and "," not in index:
            x, y = index.split("-")
            indices = [x for x in range(int(x), int(y) + 1)]

        elif "," in index and "-" not in index:
            splits = index.split(",")
            for sp in splits:
                if "!" in sp:
                    rm.append(int(sp))
                else:
                    indices.append(int(sp))

        elif groups is not None and index in groups:
            files = [x for x in all_items if x in groups[index]]
            indices = [all_items.index(x) for x in files]

        else:
            if len(all_items) < int(index) or int(index) < 0:
                indices = []
            else:
                indices = [int(index)]

        indices = [i for i in indices if i not in rm]
        try:
            files = np.asarray(all_items)[indices].tolist()
        except IndexError:
            logging.warning("Index out of range")
            files = []

        return files

    except ValueError:
        return []


class FileDictWidget(QWidget):
    def __init__(self, main_win, mode):
        """A widget to assign MRI-Subjects or Empty-Room-Files to file(s)"""

        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr
        self.mode = mode
        if mode == "mri":
            self.title = "Assign MEEG-Files to a FreeSurfer-Subject"
            self.subtitles = ("Choose a MEEG-File", "Choose a FreeSurfer-Subject")
        else:
            self.title = "Assign MEEG-File to a Empty-Room-File"
            self.subtitles = ("Choose a MEEG-File", "Choose an Empty-Room-File")

        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        if self.mode == "mri":
            assign_widget = AssignWidget(
                self.pr.all_meeg,
                self.pr.all_fsmri,
                self.pr.meeg_to_fsmri,
                title=self.title,
                subtitles=self.subtitles,
            )
        else:
            assign_widget = AssignWidget(
                self.pr.all_meeg,
                self.pr.all_erm,
                self.pr.meeg_to_erm,
                title=self.title,
                subtitles=self.subtitles,
            )
        layout.addWidget(assign_widget)

        self.setLayout(layout)


class FileDictDialog(FileDictWidget):
    def __init__(self, main_win, mode):
        super().__init__(main_win, mode)

        dialog = QDialog(main_win)

        close_bt = QPushButton("Close", self)
        close_bt.clicked.connect(dialog.close)
        self.layout().addWidget(close_bt)

        dialog.setLayout(self.layout())

        set_ratio_geometry(0.6, self)

        dialog.open()


class CopyBadsDialog(QDialog):
    def __init__(self, parent_w):
        super().__init__(parent_w)

        self.parent_w = parent_w
        self.all_files = parent_w.pr.all_meeg + parent_w.pr.all_erm
        self.bad_channels_dict = parent_w.pr.meeg_bad_channels

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QGridLayout()

        from_l = QLabel("Copy from:")
        layout.addWidget(from_l, 0, 0)
        to_l = QLabel("Copy to:")
        layout.addWidget(to_l, 0, 1)

        # Preselect the current selected MEEG
        self.copy_from = [self.parent_w.current_obj.name]
        self.copy_tos = []

        self.listw1 = CheckList(
            self.all_files, self.copy_from, ui_buttons=False, one_check=True
        )
        self.listw2 = CheckList(self.all_files, self.copy_tos)

        layout.addWidget(self.listw1, 1, 0)
        layout.addWidget(self.listw2, 1, 1)

        copy_bt = QPushButton("Copy")
        copy_bt.clicked.connect(self.copy_bads)
        layout.addWidget(copy_bt, 2, 0)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt, 2, 1)

        self.setLayout(layout)

    def copy_bads(self):
        # Check, that at least one item is selected in each list
        # and that the copy_from-item is in meeg_bad_channels
        if (
            len(self.copy_from) * len(self.copy_tos) > 0
            and self.copy_from[0] in self.bad_channels_dict
        ):
            for copy_to in self.copy_tos:
                copy_bad_chs = self.bad_channels_dict[self.copy_from[0]].copy()
                copy_to_info = MEEG(copy_to, self.parent_w.mw.ct).load_info()
                # Make sure, that only channels which exist too
                # in copy_to are copied
                for rm_ch in [
                    r for r in copy_bad_chs if r not in copy_to_info["ch_names"]
                ]:
                    copy_bad_chs.remove(rm_ch)
                self.bad_channels_dict[copy_to] = copy_bad_chs


class SubBadsWidget(QWidget):
    """A Dialog to select Bad-Channels for the files."""

    def __init__(self, main_win):
        """
        :param main_win: The parent-window for the dialog
        """
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr
        self.setWindowTitle("Assign bad_channels for your files")
        self.all_files = self.pr.all_meeg + self.pr.all_erm
        self.bad_chkbts = {}
        self.info_dict = {}
        self.current_obj = None
        self.raw = None
        self.raw_fig = None

        self.init_ui()

    def init_ui(self):
        self.layout = QGridLayout()

        file_list = self.pr.all_meeg
        self.files_widget = CheckDictList(
            file_list, self.pr.meeg_bad_channels, title="Files"
        )
        self.files_widget.currentChanged.connect(self.bad_dict_selected)
        self.files_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred
        )
        self.layout.addWidget(self.files_widget, 0, 0)

        self.bt_scroll = QScrollArea()
        self.bt_scroll.setWidgetResizable(True)
        self.layout.addWidget(self.bt_scroll, 0, 1)

        # Add Buttons
        self.bt_layout = QHBoxLayout()

        plot_bt = QPushButton("Plot raw")
        plot_bt.clicked.connect(self.plot_raw_bad)
        self.bt_layout.addWidget(plot_bt)

        find_bads_bt = QPushButton("Find bads")
        find_bads_bt.clicked.connect(self.find_bads)
        self.bt_layout.addWidget(find_bads_bt)

        copy_bt = QPushButton("Copy Bads")
        copy_bt.clicked.connect(partial(CopyBadsDialog, self))
        self.bt_layout.addWidget(copy_bt)

        self.save_raw_annot = QCheckBox("Save Annotations")
        self.bt_layout.addWidget(self.save_raw_annot)

        self.layout.addLayout(self.bt_layout, 1, 0, 1, 2)
        self.setLayout(self.layout)

    def update_selection(self):
        # Clear entries
        for bt in self.bad_chkbts:
            self.bad_chkbts[bt].setChecked(False)

        # Catch Channels, which are present in meeg_bad_channels,
        # but not in bad_chkbts
        # Then load existing bads for choice
        for bad in self.current_obj.bad_channels:
            if bad in self.bad_chkbts:
                self.bad_chkbts[bad].setChecked(True)
            else:
                # Remove bad channel from bad_channels if not existing
                # in bad_chkbts (and thus not in ch_names)
                self.current_obj.bad_channels.remove(bad)

    def _make_bad_chbxs(self, info):
        time.sleep(1)
        # Store info in dictionary
        self.info_dict[self.current_obj.name] = info

        chbx_w = QWidget()
        chbx_w.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.chbx_layout = QGridLayout()
        row = 0
        column = 0
        h_size = 0
        # Currently, you have to fine-tune the max_h_size,
        # because it doesn't seem to reflect exactly the actual width
        max_h_size = int(self.bt_scroll.geometry().width() * 0.85)

        self.bad_chkbts = {}

        # Make Checkboxes for channels in info
        for ch_name in info["ch_names"]:
            chkbt = QCheckBox(ch_name)
            chkbt.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            chkbt.clicked.connect(self.bad_ckbx_assigned)
            self.bad_chkbts[ch_name] = chkbt
            h_size += chkbt.sizeHint().width()
            if h_size > max_h_size:
                column = 0
                row += 1
                h_size = chkbt.sizeHint().width()
            self.chbx_layout.addWidget(chkbt, row, column)
            column += 1

        chbx_w.setLayout(self.chbx_layout)

        # Remove previous buttons if existing
        if self.bt_scroll.widget():
            self.bt_scroll.takeWidget()

        self.bt_scroll.setWidget(chbx_w)
        self.update_selection()

    def make_bad_chbxs(self):
        if self.current_obj:
            # Don't load info twice from file
            if self.current_obj.name in self.info_dict:
                self._make_bad_chbxs(self.info_dict[self.current_obj.name])
            else:
                worker_dlg = WorkerDialog(
                    self, self.current_obj.load_info, title="Loading Channels..."
                )
                worker_dlg.thread_finished.connect(self._make_bad_chbxs)

    def bad_dict_selected(self, current, _):
        self.current_obj = MEEG(current, self.ct)

        # Close current Plot-Window
        if self.raw_fig:
            if hasattr(self.raw_fig, "canvas"):
                plt.close(self.raw_fig)
            else:
                self.raw_fig.close()

        self.make_bad_chbxs()

    def bad_ckbx_assigned(self):
        bad_channels = [ch for ch in self.bad_chkbts if self.bad_chkbts[ch].isChecked()]
        self.current_obj.set_bad_channels(bad_channels)

    def set_chkbx_enable(self, enable):
        for chkbx in self.bad_chkbts:
            self.bad_chkbts[chkbx].setEnabled(enable)

    def get_selected_bads(self, _, meeg, raw, raw_type):
        self.current_obj.set_bad_channels(raw.info["bads"])
        self.update_selection()
        self.set_chkbx_enable(True)

        if self.save_raw_annot.isChecked():
            WorkerDialog(
                self,
                meeg.save,
                data_type=raw_type,
                data=raw,
                show_console=True,
                title="Saving raw with Annotations",
            )

        self.raw_fig = None

    def plot_raw_bad(self):
        # Disable CheckBoxes to avoid confusion
        # (Bad-Selection only goes unidirectional from Plot>GUI)
        self.set_chkbx_enable(False)

        plot_dialog = QDialog(self)
        plot_dialog.setWindowTitle("Opening raw-Plot...")
        plot_dialog.open()

        plot_raw(self.current_obj, show_plots=True, close_func=self.get_selected_bads)
        plot_dialog.close()

    def find_bads(self):
        wd = WorkerDialog(
            self,
            find_bads,
            meeg=self.current_obj,
            n_jobs=Settings().get("n_jobs"),
            show_console=True,
            show_buttons=True,
            close_directly=False,
            return_exception=False,
            title="Finding bads with maxwell filter...",
        )
        wd.thread_finished.connect(self.update_selection)

    def resizeEvent(self, event):
        if self.current_obj:
            self.make_bad_chbxs()
            self.update_selection()
        event.accept()

    def closeEvent(self, event):
        if self.raw_fig:
            plt.close(self.raw_fig)
            event.accept()
        else:
            event.accept()


class SubBadsDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)

        layout = QVBoxLayout()

        bads_widget = SubBadsWidget(main_win)
        layout.addWidget(bads_widget)

        close_bt = QPushButton("Close", self)
        close_bt.clicked.connect(self.close)
        bads_widget.bt_layout.addWidget(close_bt)

        self.setLayout(layout)

        set_ratio_geometry(0.8, self)

        self.show()


class EventIDGui(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr

        self.name = None
        self.event_id = {}
        self.queries = {}
        self.labels = []
        self.checked_labels = []

        self.layout = QVBoxLayout()
        self.init_ui()

        self.show()

    def init_ui(self):
        list_layout = QHBoxLayout()

        self.files = CheckDictList(
            self.pr.all_meeg, self.pr.meeg_event_id, title="Files"
        )
        self.files.currentChanged.connect(self.file_selected)

        list_layout.addWidget(self.files)

        event_id_layout = QVBoxLayout()

        self.event_id_widget = EditDict(
            self.event_id, ui_buttons=True, title="Event-ID"
        )
        # Connect editing of Event-ID-Table to update of Check-List
        self.event_id_widget.dataChanged.connect(self.update_check_list)
        self.event_id_widget.setToolTip(
            "Add a Trial-Descriptor (as key) for each Event-ID (as value) "
            "you want to include it in you analysis.\n"
            "You can assign multiple descriptors per ID by "
            'separating them by "/"'
        )
        event_id_layout.addWidget(self.event_id_widget)

        self.event_id_label = QLabel()
        event_id_layout.addWidget(self.event_id_label)

        list_layout.addLayout(event_id_layout)

        self.query_widget = EditDict(
            self.queries, ui_buttons=True, title="Metadata-Queries"
        )
        self.query_widget.setToolTip(
            "Add Metadata-Queries as value for trials which are named with key"
        )
        self.query_widget.dataChanged.connect(self.update_check_list)
        list_layout.addWidget(self.query_widget)

        self.check_widget = CheckList(title="Select IDs")
        list_layout.addWidget(self.check_widget)

        self.layout.addLayout(list_layout)

        bt_layout = QHBoxLayout()

        apply_bt = QPushButton("Apply to")
        apply_bt.clicked.connect(partial(EvIDApply, self))
        bt_layout.addWidget(apply_bt)

        show_events = QPushButton("Show events")
        show_events.clicked.connect(self.show_events)
        bt_layout.addWidget(show_events)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        bt_layout.addWidget(close_bt)

        self.layout.addLayout(bt_layout)

        self.setLayout(self.layout)

    def get_event_id(self):
        """Get unique event-ids from events."""
        if self.name in self.pr.meeg_event_id:
            self.event_id = self.pr.meeg_event_id[self.name]
        else:
            self.event_id = {}
        self.event_id_widget.replace_data(self.event_id)

        meeg = MEEG(self.name, self.ct, suppress_warnings=True)
        try:
            # Load events from File
            events = meeg.load_events()
        except FileNotFoundError:
            label_text = f"No events found for {self.name}"
        else:
            label_text = f"events found: {np.unique(events[:, 2])}"

        try:
            # Load epochs from File
            epochs = meeg.load_epochs()
            assert epochs.metadata is not None
        except (FileNotFoundError, AssertionError):
            self.query_widget.setEnabled(False)
            label_text += "\nNo metadata found"
        else:
            self.query_widget.setEnabled(True)
            label_text += "\nMetadata found"

        self.event_id_label.setText(label_text)

    def save_event_id(self):
        if self.name:
            if len(self.event_id) > 0:
                # Write Event-ID to Project
                self.pr.meeg_event_id[self.name] = self.event_id

                # Get selected Trials, add queries and write them to meeg.pr
                sel_event_id = {}
                for label in self.checked_labels:
                    if label in self.queries:
                        sel_event_id[label] = self.queries[label]
                    else:
                        sel_event_id[label] = None
                self.pr.sel_event_id[self.name] = sel_event_id

    def file_selected(self, current, _):
        """Called when File from file_widget is selected."""
        # Save event_id for previous file
        self.save_event_id()

        # Get event-id for selected file and update widget
        self.name = current
        self.get_event_id()

        # Load checked trials
        if self.name in self.pr.sel_event_id:
            # Update query-widget
            if self.query_widget.isEnabled():
                sel_trials = self.pr.sel_event_id[self.name]
                if not isinstance(sel_trials, dict):
                    sel_trials = {k: None for k in sel_trials}
                self.queries = {k: v for k, v in sel_trials.items() if v is not None}
                self.query_widget.replace_data(self.queries)
            # Legacy to allow reading lists before
            # they were changed to dicts for queries
            self.checked_labels = list(self.pr.sel_event_id[self.name])
        else:
            self.checked_labels = []
        self.update_check_list()

    # ToDo: Make all combinations possible and also int-keys (can't split)
    def update_check_list(self):
        self.labels = [k for k in self.queries.keys()]
        # Get selectable trials and update widget
        prelabels = [i.split("/") for i in self.event_id.keys() if i != ""]
        if len(prelabels) > 0:
            # Concatenate all lists
            conc_labels = prelabels[0]
            if len(prelabels) > 1:
                for item in prelabels[1:]:
                    conc_labels += item
            # Make sure that only unique labels exist
            self.labels += list(set(conc_labels))

            # Make sure, that only trials, which exist in event_id exist
            for chk_label in self.checked_labels:
                if (
                    not any(chk_label in key for key in self.event_id)
                    and chk_label not in self.queries
                ):
                    self.checked_labels.remove(chk_label)
        else:
            self.labels = []

        self.check_widget.replace_data(self.labels)
        self.check_widget.replace_checked(self.checked_labels)

    def show_events(self):
        try:
            meeg = MEEG(self.name, self.ct, suppress_warnings=True)
            events = meeg.load_events()
            mne.viz.plot_events(events, event_id=self.event_id or None, show=True)
        except FileNotFoundError:
            warning_message(f"No events found for {self.name}", parent=self)

    def closeEvent(self, event):
        # Save event_id for last selected file
        self.save_event_id()
        event.accept()


class EvIDApply(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.p = parent

        # Save to make sel_event_id available in apply_evid
        self.p.save_event_id()

        self.apply_to = []

        self.layout = QVBoxLayout()
        self.init_ui()

        self.open()

    def init_ui(self):
        label = QLabel(f"Apply {self.p.name} to:")
        self.layout.addWidget(label)

        self.check_listw = CheckList(self.p.pr.all_meeg, self.apply_to)
        self.layout.addWidget(self.check_listw)

        bt_layout = QHBoxLayout()

        apply_bt = QPushButton("Apply")
        apply_bt.clicked.connect(self.apply_evid)
        bt_layout.addWidget(apply_bt)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        bt_layout.addWidget(close_bt)

        self.layout.addLayout(bt_layout)
        self.setLayout(self.layout)

    def apply_evid(self):
        for file in self.apply_to:
            # Avoid with copy that CheckList-Model changes selected
            # for all afterwards (same reference)
            self.p.pr.meeg_event_id[file] = self.p.pr.meeg_event_id[self.p.name].copy()
            self.p.pr.sel_event_id[file] = self.p.pr.sel_event_id[self.p.name].copy()


class CopyTrans(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr

        # Get MEEGs, where a trans-file is already existing
        self.from_meegs = []
        for meeg_name in self.pr.all_meeg:
            meeg = MEEG(meeg_name, self.ct)
            if isfile(meeg.trans_path):
                self.from_meegs.append(meeg_name)

        # Get the other MEEGs (wihtout trans-file)
        self.to_meegs = [
            meeg for meeg in self.pr.all_meeg if meeg not in self.from_meegs
        ]

        self.current_meeg = None
        self.copy_tos = []

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QGridLayout()

        from_list = SimpleList(self.from_meegs, title="From:")
        from_list.currentChanged.connect(self.from_selected)
        layout.addWidget(from_list, 0, 0)

        self.to_list = CheckList(
            self.to_meegs, self.copy_tos, ui_button_pos="bottom", title="To:"
        )
        layout.addWidget(self.to_list, 0, 1)

        copy_bt = QPushButton("Copy")
        copy_bt.clicked.connect(self.copy_trans)
        layout.addWidget(copy_bt, 1, 0)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt, 1, 1)

        self.setLayout(layout)

    def _compare_digs(self, worker_signals):
        self.copy_tos.clear()
        # Get Digitization points
        current_dig = self.current_meeg.load_info()["dig"]

        # Add all meeg, which have the exact same digitization points
        # (assuming, that they can use the same trans-file)
        worker_signals.pgbar_max.emit(len(self.to_meegs))
        for n, to_meeg in enumerate(self.to_meegs):
            worker_signals.pgbar_text.emit(f"Comparing: {to_meeg}")
            if MEEG(to_meeg, self.ct).load_info()["dig"] == current_dig:
                self.copy_tos.append(to_meeg)
            worker_signals.pgbar_n.emit(n + 1)

        self.to_list.content_changed()

    def from_selected(self, current_meeg):
        self.current_meeg = MEEG(current_meeg, self.ct)
        WorkerDialog(self, self._compare_digs, show_buttons=False, show_console=False)

    def copy_trans(self):
        if self.current_meeg:
            from_path = self.current_meeg.trans_path

            for copy_to in self.copy_tos:
                to_meeg = MEEG(copy_to, self.ct)
                to_path = to_meeg.trans_path

                shutil.copy2(from_path, to_path)

                self.to_meegs.remove(copy_to)

            self.copy_tos.clear()
            self.to_list.content_changed()


class ICASelect(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr
        self.current_obj = None
        self.parameters = {}
        self.chkbxs = {}

        self.max_width, self.max_height = set_ratio_geometry(0.8)
        self.setMaximumSize(self.max_width, self.max_height)

        self.init_ui()
        self.show()

    def init_ui(self):
        self.main_layout = QVBoxLayout()
        list_layout = QHBoxLayout()

        self.file_list = CheckDictList(self.pr.all_meeg, self.pr.meeg_ica_exclude)
        self.file_list.currentChanged.connect(self.obj_selected)
        list_layout.addWidget(self.file_list)

        # Add Checkboxes for Components
        comp_scroll = QScrollArea()
        comp_widget = QWidget()
        self.comp_chkbx_layout = QGridLayout()

        n_components = self.pr.parameters[self.pr.p_preset]["n_components"]
        for idx in range(n_components):
            chkbx = QCheckBox(str(idx))
            chkbx.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
            chkbx.clicked.connect(self.component_selected)
            self.chkbxs[idx] = chkbx
            self.comp_chkbx_layout.addWidget(chkbx, idx // 5, idx % 5)

        comp_widget.setLayout(self.comp_chkbx_layout)
        comp_scroll.setWidget(comp_widget)
        list_layout.addWidget(comp_scroll)

        bt_layout = QVBoxLayout()

        plot_comp_bt = QPushButton("Plot Components")
        plot_comp_bt.clicked.connect(self.plot_components)
        bt_layout.addWidget(plot_comp_bt)

        # Create Parameter-GUI which stores parameter in dictionary
        # (not the same as project.parameters)
        ica_source_data_param = ComboGui(
            data=self.parameters,
            name="ica_source_data",
            options=[
                "raw",
                "raw_filtered",
                "epochs",
                "epochs_eog",
                "epochs_ecg",
                "evoked",
                "evoked_eog",
                "evoked_ecg",
            ],
            default="raw_filtered",
        )
        bt_layout.addWidget(ica_source_data_param)

        plot_source_bt = QPushButton("Plot Source")
        plot_source_bt.clicked.connect(self.plot_sources)
        bt_layout.addWidget(plot_source_bt)

        ica_overlay_data_param = ComboGui(
            data=self.parameters,
            name="ica_overlay_data",
            options=["raw", "raw_filtered", "evoked", "evoked_eog", "evoked_ecg"],
            default="raw_filtered",
        )
        bt_layout.addWidget(ica_overlay_data_param)

        plot_overlay_bt = QPushButton("Plot Overlay")
        plot_overlay_bt.clicked.connect(self.plot_overlay)
        bt_layout.addWidget(plot_overlay_bt)

        plot_overlay_bt = QPushButton("Plot Properties")
        plot_overlay_bt.clicked.connect(self.plot_properties)
        bt_layout.addWidget(plot_overlay_bt)

        close_plots_bt = QPushButton("Close Plots")
        close_plots_bt.clicked.connect(partial(plt.close, "all"))
        bt_layout.addWidget(close_plots_bt)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        bt_layout.addWidget(close_bt)

        list_layout.addLayout(bt_layout)
        self.main_layout.addLayout(list_layout)

        self.setLayout(self.main_layout)

    def update_chkbxs(self):
        # Check, if object is already in ica_exclude
        if self.current_obj.name in self.pr.meeg_ica_exclude:
            selected_components = self.pr.meeg_ica_exclude[self.current_obj.name]
        else:
            selected_components = []

        # Clear all checkboxes
        for idx in self.chkbxs:
            self.chkbxs[idx].setChecked(False)

        # Select components
        for idx in selected_components:
            if idx in self.chkbxs:
                self.chkbxs[idx].setChecked(True)
            else:
                # Remove idx if not in range(n_components)
                self.pr.meeg_ica_exclude[self.current_obj.name].remove(idx)

    def obj_selected(self, current_name):
        self.current_obj = MEEG(current_name, self.ct)
        self.update_chkbxs()

    def component_selected(self):
        if self.current_obj:
            self.pr.meeg_ica_exclude[self.current_obj.name] = [
                idx for idx in self.chkbxs if self.chkbxs[idx].isChecked()
            ]
        self.file_list.content_changed()

    def set_chkbx_enable(self, enable):
        for chkbx in self.chkbxs:
            self.chkbxs[chkbx].setEnabled(enable)

    def get_selected_components(self, _, meeg, ica):
        self.set_chkbx_enable(True)
        meeg.set_ica_exclude(ica.exclude)
        self.update_chkbxs()
        self.file_list.content_changed()

    def plot_components(self):
        if self.current_obj:
            # Disable CheckBoxes to avoid confusion
            # (Bad-Selection only goes unidirectional from Plot>GUI)
            self.set_chkbx_enable(False)
            dialog = QDialog(self)
            dialog.setWindowTitle("Opening...")
            dialog.open()
            with gui_error():
                plot_ica_components(
                    meeg=self.current_obj,
                    show_plots=True,
                    close_func=self.get_selected_components,
                )
            dialog.close()

    def plot_sources(self):
        if self.current_obj:
            # Disable CheckBoxes to avoid confusion
            # (Bad-Selection only goes unidirectional from Plot>GUI)
            self.set_chkbx_enable(False)
            dialog = QDialog(self)
            dialog.setWindowTitle("Opening...")
            dialog.open()

            with gui_error():
                plot_ica_sources(
                    meeg=self.current_obj,
                    ica_source_data=self.parameters["ica_source_data"],
                    show_plots=True,
                    close_func=self.get_selected_components,
                )
            dialog.close()

    def plot_overlay(self):
        if self.current_obj:
            # Disable CheckBoxes to avoid confusion
            # (Bad-Selection only goes unidirectional from Plot>GUI)
            dialog = QDialog(self)
            dialog.setWindowTitle("Opening...")
            dialog.open()

            with gui_error():
                plot_ica_overlay(
                    meeg=self.current_obj,
                    ica_overlay_data=self.parameters["ica_overlay_data"],
                    show_plots=True,
                )
            dialog.close()

    def plot_properties(self):
        if self.current_obj:
            # Disable CheckBoxes to avoid confusion
            # (Bad-Selection only goes unidirectional from Plot>GUI)
            dialog = QDialog(self)
            dialog.setWindowTitle("Opening...")
            dialog.open()
            with gui_error():
                plot_ica_properties(meeg=self.current_obj, show_plots=True)
            dialog.close()


class ReloadRaw(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct
        self.pr = main_win.ct.pr

        self.init_ui()
        self.open()

    def init_ui(self):
        layout = QVBoxLayout()

        self.raw_list = SimpleList(self.pr.all_meeg, title="Select raw to reload")
        layout.addWidget(self.raw_list)

        reload_bt = QPushButton("Reload")
        reload_bt.clicked.connect(self.start_reload)
        layout.addWidget(reload_bt)

        close_bt = QPushButton("Close")
        close_bt.clicked.connect(self.close)
        layout.addWidget(close_bt)

        self.setLayout(layout)

    def reload_raw(self, selected_raw, raw_path):
        meeg = MEEG(selected_raw, self.ct)
        raw = mne.io.read_raw(raw_path, preload=True)
        meeg.save_raw(raw)
        logging.info(f"Reloaded raw for {selected_raw}")

    def start_reload(self):
        # Not with partial because otherwise the clicked-arg
        # from clicked goes into *args
        selected_raw = self.raw_list.get_current()
        raw_path = compat.getopenfilename(self, "Select raw for Reload")[0]
        if raw_path:
            WorkerDialog(
                self,
                self.reload_raw,
                selected_raw=selected_raw,
                raw_path=raw_path,
                show_console=True,
                title=f"Reloading raw for {selected_raw}",
            )


class ExportDialog(QDialog):
    def __init__(self, main_win):
        super().__init__(main_win)
        self.mw = main_win
        self.ct = main_win.ct

        self.common_types = []
        self.selected_types = []
        self.dest_path = None
        self.export_paths = {}

        self._get_common_types()
        self._init_ui()
        self.open()

    def _get_common_types(self):
        for meeg_name in self.ct.pr.sel_meeg:
            meeg = MEEG(meeg_name, self.ct)
            meeg.get_existing_paths()
            type_set = set(meeg.existing_paths.keys())
            if isinstance(self.common_types, list):
                self.common_types = type_set
            else:
                self.common_types = self.common_types & type_set
            self.export_paths[meeg_name] = meeg.existing_paths

    def _get_destination(self):
        dest = compat.getexistingdirectory(self, "Select Destination-Folder")
        if dest:
            self.dest_path = dest

    def _init_ui(self):
        layout = QVBoxLayout()
        self.dest_label = QLabel("<No Destination-Folder set>")
        layout.addWidget(self.dest_label)
        dest_bt = QPushButton("Set Destination-Folder")
        dest_bt.clicked.connect(self._get_destination)
        layout.addWidget(dest_bt)
        layout.addWidget(QLabel())
        layout.addWidget(
            SimpleList(
                self.ct.pr.sel_meeg,
                title="Export selected data for the following MEEG-Files:",
            )
        )
        layout.addWidget(
            CheckList(
                list(self.common_types),
                self.selected_types,
                title="Selected Data-Types",
            )
        )
        export_bt = QPushButton("Export")
        export_bt.clicked.connect(self.export_data)
        layout.addWidget(export_bt)
        self.setLayout(layout)

    def export_data(self):
        if self.dest_path:
            logging.info("Starting Export\n")
            for meeg_name, path_types in self.export_paths.items():
                os.mkdir(join(self.dest_path, meeg_name))
                for path_type in [pt for pt in path_types if pt in self.selected_types]:
                    paths = path_types[path_type]
                    logging.info(f"\r{meeg_name}: Copying {path_type}...")
                    for src_path in paths:
                        dest_name = Path(src_path).name
                        shutil.copy2(
                            src_path, join(self.dest_path, meeg_name, dest_name)
                        )
                    logging.info(f"\r{meeg_name}: Copied {path_type}!")

        else:
            warning_message("Destination-Path not set!", parent=self)
