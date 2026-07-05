from __future__ import annotations

from copy import copy
from functools import partial
from typing import Any

import mne
import numpy as np
from qtpy.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mne_nodes.gui.base_widgets import CheckList, SimpleDialog, SimpleList
from mne_nodes.gui.gui_utils import center
from mne_nodes.pipeline.controller import Controller

from .param import Param
from .utils import convert_list_to_string


class LabelPicker(mne.viz.Brain):
    def __init__(
        self, paramdlg, parcellation, surface, selected, list_changed_slot, title
    ):
        super().__init__(
            paramdlg._fsmri.name,
            surf=surface,
            title=title,
            subjects_dir=paramdlg.ct.subjects_dir,
            background=(0, 0, 0),
        )
        self._renderer.plotter.show()
        self.paramdlg = paramdlg
        self.paramw = paramdlg.paramw

        self.parcellation = parcellation
        self.selected = selected
        self.list_changed_slot = list_changed_slot

        self._shown_labels = []

        self.add_text(0, 0.9, "", color="w", font_size=14, name="title")

        self._set_annotations(parcellation)
        self._init_picking()

        for label_name in selected:
            hemi = label_name[-2:]
            self._add_label_name(label_name, hemi)

    def _set_annotations(self, parcellation):
        fsmri = self.paramdlg._fsmri
        self.parcellation = parcellation
        self.clear_glyphs()
        self.remove_labels()
        self.remove_annotations()
        labels = fsmri.get_labels(parcellation=parcellation)
        if parcellation == "Other":
            for label in labels:
                self.add_label(label, borders=True, color="k", alpha=0.75)
        else:
            self.add_annotation(
                parcellation, borders=True, color="k", alpha=0.75, remove_existing=True
            )

        for hemi in self._hemis:
            hemi_labels = [lb for lb in labels if lb.hemi == hemi]
            self._vertex_to_label_id[hemi] = np.full(self.geo[hemi].coords.shape[0], -1)
            self._annotation_labels[hemi] = hemi_labels
            for idx, hemi_label in enumerate(hemi_labels):
                self._vertex_to_label_id[hemi][hemi_label.vertices] = idx

        self._actors["text"]["title"].SetInput(
            f"Subject={self.paramdlg._fsmri.name}, Parcellation={parcellation}\n"
            f"Select labels by clicking on them"
        )

    def _init_picking(self):
        from vtkmodules.vtkCommonCore import vtkCommand
        from vtkmodules.vtkRenderingCore import vtkCellPicker

        self._mouse_no_mvt = -1
        add_obs = self._renderer.plotter.iren.add_observer
        add_obs(vtkCommand.RenderEvent, self._on_mouse_move)
        add_obs(vtkCommand.LeftButtonPressEvent, self._on_button_press)
        add_obs(vtkCommand.EndInteractionEvent, self._on_button_release)
        self._renderer.plotter.picker = vtkCellPicker()
        self._renderer.plotter.picker.AddObserver(
            vtkCommand.EndPickEvent, self._label_picked
        )

    def _label_picked(self, vtk_picker, _):
        cell_id = vtk_picker.GetCellId()
        mesh = vtk_picker.GetDataSet()
        if mesh is not None:
            hemi = mesh._hemi
            if mesh is None or cell_id == -1 or not self._mouse_no_mvt:
                return
            pos = np.array(vtk_picker.GetPickPosition())
            vtk_cell = mesh.GetCell(cell_id)
            cell = [
                vtk_cell.GetPointId(point_id)
                for point_id in range(vtk_cell.GetNumberOfPoints())
            ]
            vertices = mesh.points[cell]
            idx = np.argmin(abs(vertices - pos), axis=0)
            vertex_id = cell[idx[0]]

            label_id = self._vertex_to_label_id[hemi][vertex_id]
            label = self._annotation_labels[hemi][label_id]

            if label.name in self.selected:
                self._remove_label_name(label.name, hemi)
                self.selected.remove(label.name)
            else:
                self._add_label_name(label.name, hemi, label)
                self.selected.append(label.name)
            self.list_changed_slot()
            self.paramdlg.update_selected_display()

            if "label" in self._actors["text"]:
                self.remove_text("label")
            if label.color is not None:
                color = label.color[:3]
                opacity = label.color[-1]
            else:
                color = "w"
                opacity = 1
            self.add_text(
                0,
                0.05,
                label.name,
                color=color,
                opacity=opacity,
                font_size=12,
                name="label",
            )

    def _add_label_name(self, label_name, hemi, label=None):
        if label is None:
            for lb in self._annotation_labels[hemi]:
                if lb.name == label_name:
                    label = lb
                    break
        if label is not None:
            self.add_label(label, borders=False)
            self._shown_labels.append(label_name)

    def _remove_label_name(self, label_name, hemi):
        self._layered_meshes[hemi].remove_overlay(label_name)
        self._shown_labels.remove(label_name)
        self._renderer._update()

    def isclosed(self):
        if self.plotter is None:
            self._closed = True
        return self._closed

    def close(self):
        if self.plotter is not None:
            super().close()
        self._closed = True


class LabelDialog(SimpleDialog):
    def __init__(self, paramw):
        self.main_widget = QWidget()
        super().__init__(
            self.main_widget,
            parent=paramw,
            title="Choose a label!",
            window_title="Label Picker",
            modal=False,
        )
        self.paramw = paramw
        self.ct = paramw.data

        self._parc_picker = None
        self._extra_picker = None
        self._fsmri = None
        self._parcellation = None
        self._surface = None
        self._parc_labels = []
        self._selected_parc_labels = copy(paramw.value) or []
        self._extra_labels = []
        self._selected_extra_labels = copy(paramw.value) or []

        self.resize(400, 800)
        center(self)

        self._init_layout()

        self._subject_changed()
        self._surface_changed()

    def _init_layout(self):
        layout = QVBoxLayout(self.main_widget)

        layout.addWidget(QLabel("Choose a subject:"))
        self.fsmri_cmbx = QComboBox()
        self.fsmri_cmbx.addItems(self.ct.pr.all_fsmri)
        self.fsmri_cmbx.activated.connect(self._subject_changed)
        layout.addWidget(self.fsmri_cmbx)

        layout.addWidget(QLabel("Choose a parcellation:"))
        self.parcellation_cmbx = QComboBox()
        self.parcellation_cmbx.activated.connect(self._parc_changed)
        layout.addWidget(self.parcellation_cmbx)

        layout.addWidget(QLabel("Choose a surface:"))
        self.surface_cmbx = QComboBox()
        self.surface_cmbx.addItems(["inflated", "pial", "white"])
        self.surface_cmbx.activated.connect(self._surface_changed)
        layout.addWidget(self.surface_cmbx)

        self.selected_display = SimpleList(
            data=self._selected_parc_labels + self._selected_extra_labels,
            title="Selected Labels",
        )
        layout.addWidget(self.selected_display)

        self.parc_label_list = CheckList(
            data=self._parc_labels,
            checked=self._selected_parc_labels,
            ui_buttons=True,
            ui_button_pos="bottom",
            title="Parcellation Labels",
        )
        self.parc_label_list.checkedChanged.connect(
            partial(self._labels_changed, picker_name="parcellation")
        )
        layout.addWidget(self.parc_label_list)

        self.extra_label_list = CheckList(
            data=self._extra_labels,
            checked=self._selected_extra_labels,
            ui_buttons=True,
            ui_button_pos="bottom",
            title="Extra Labels",
        )
        self.extra_label_list.checkedChanged.connect(
            partial(self._labels_changed, picker_name="extra")
        )
        layout.addWidget(self.extra_label_list)

        self.choose_parc_bt = QPushButton("Choose Parcellation Labels")
        self.choose_parc_bt.clicked.connect(self._open_parc_picker)
        layout.addWidget(self.choose_parc_bt)

        self.choose_extra_bt = QPushButton("Choose Extra Labels")
        self.choose_extra_bt.clicked.connect(self._open_extra_picker)
        layout.addWidget(self.choose_extra_bt)

    def _subject_changed(self):
        self._fsmri = None

        self.parcellation_cmbx.clear()
        self.parcellation_cmbx.addItems(self._fsmri.parcellations)

        self._extra_labels.clear()
        self._extra_labels += [lb.name for lb in self._fsmri.labels["Other"]]
        self.extra_label_list.content_changed()

        old_selected_extra = self._selected_extra_labels.copy()
        self._selected_extra_labels.clear()
        self._selected_extra_labels += [
            lb for lb in old_selected_extra if lb in self._extra_labels
        ]
        self.extra_label_list.content_changed()

        all_labels_exept_other = []
        for parc_name, labels in self._fsmri.labels.items():
            if parc_name != "Other":
                all_labels_exept_other += [lb.name for lb in labels]
        old_selected_parc = self._selected_parc_labels.copy()
        self._selected_parc_labels.clear()
        self._selected_parc_labels += [
            lb for lb in old_selected_parc if lb in all_labels_exept_other
        ]

        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker.close()
            self._open_parc_picker()
        if self._extra_picker is not None and not self._extra_picker.isclosed():
            self._extra_picker.close()
            self._open_extra_picker()

        self._parc_changed()

    def _parc_changed(self):
        self._parc_labels.clear()

        self._parcellation = self.parcellation_cmbx.currentText()
        if self._parcellation in self._fsmri.labels:
            self._parc_labels += [
                lb.name for lb in self._fsmri.labels[self._parcellation]
            ]

        self.parc_label_list.content_changed()

        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker._set_annotations(self._parcellation)
            for label_name in [
                lb for lb in self._selected_parc_labels if lb in self._parc_labels
            ]:
                hemi = label_name[-2:]
                self._parc_picker._add_label_name(label_name, hemi)

    def _surface_changed(self):
        self._surface = self.surface_cmbx.currentText()
        if self._parc_picker is not None and not self._parc_picker.isclosed():
            self._parc_picker.close()
            self._open_parc_picker()

    def update_selected_display(self):
        self.selected_display.replace_data(
            self._selected_parc_labels + self._selected_extra_labels
        )

    def _labels_changed(self, labels, picker_name):
        picker = (
            self._parc_picker if picker_name == "parcellation" else self._extra_picker
        )
        if picker is not None:
            shown_labels = picker._shown_labels
            for add_name in [lb for lb in labels if lb not in shown_labels]:
                hemi = add_name[-2:]
                picker._add_label_name(add_name, hemi)
            for remove_name in [lb for lb in shown_labels if lb not in labels]:
                hemi = remove_name[-2:]
                picker._remove_label_name(remove_name, hemi)
        self.update_selected_display()

    def _open_parc_picker(self):
        self._parc_picker = LabelPicker(
            self,
            self._parcellation,
            self._surface,
            self._selected_parc_labels,
            self.parc_label_list.content_changed,
            title="Pick parcellation labels",
        )

    def _open_extra_picker(self):
        self._extra_picker = LabelPicker(
            self,
            "Other",
            self._surface,
            self._selected_extra_labels,
            self.extra_label_list.content_changed,
            title="Pick extra labels",
        )

    def closeEvent(self, event):
        self.paramw.set_param(self._selected_parc_labels + self._selected_extra_labels)
        for picker in [self._parc_picker, self._extra_picker]:
            if picker is not None and not picker.isclosed():
                picker.close()
        self.hide()


class LabelGui(Param):
    data_type = list

    def __init__(self, value_string_length: int | None = 30, **kwargs: Any):
        super().__init__(**kwargs)
        self.value_string_length = value_string_length
        if not isinstance(self.data, Controller):
            raise RuntimeError(
                "LabelGui can only used with an instance of Controller passed as data."
            )
        self._dialog = None
        self.cached_value = None
        check_list_layout = QHBoxLayout()
        self.value_label = QLabel()
        check_list_layout.addWidget(self.value_label)
        self.param_widget = QPushButton("Edit")
        self.param_widget.setSizePolicy(
            QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum
        )
        self.param_widget.clicked.connect(self.show_dialog)
        check_list_layout.addWidget(self.param_widget)
        self.init_ui(check_list_layout)

    def show_dialog(self):
        if self._dialog is None:
            self._dialog = LabelDialog(self)
            self._dialog.open()
        else:
            self._dialog.show()

    def _set_widget_value(self, value):
        if value is not None:
            self.cached_value = value
        self.value_label.setText(
            convert_list_to_string(value, self.unit, self.value_string_length)
        )

    def _get_widget_value(self):
        if self.value is None:
            if self.cached_value:
                value = self.cached_value
            else:
                value = []
            self.value_label.clear()
        else:
            value = self.value

        return value
