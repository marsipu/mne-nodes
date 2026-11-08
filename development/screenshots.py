"""Generate documentation screenshots from TOML-configured scenarios.

Every screenshot starts from a fresh, disposable project described by the
``[project]`` table of the configuration file. Its ``steps`` then click, drag,
select or call into widgets before the capture is saved, optionally with
highlight rectangles and labels drawn on top. See
``docs/source/development/screenshots.md`` for the configuration format.

Run from the repository root::

    python -m development.screenshots --output docs/source/_static/screenshots/linux
"""

import argparse
import importlib
import json
import os
import sys
import time
import tomllib
import traceback
from collections.abc import Callable, Mapping
from fnmatch import fnmatch
from importlib.resources import files
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from typing import Any

from qtpy.QtCore import QObject, QPoint, QPointF, QRectF, QSizeF, Qt
from qtpy.QtGui import QColor, QFontMetricsF, QImage, QKeySequence, QPainter, QPen
from qtpy.QtTest import QTest
from qtpy.QtWidgets import (
    QAbstractItemView,
    QAbstractScrollArea,
    QApplication,
    QComboBox,
    QGraphicsItem,
    QTabWidget,
    QWidget,
)

import mne_nodes
from mne_nodes.backend import controller as controller_module
from mne_nodes.backend.controller import Controller, default_config
from mne_nodes.backend.plugin_package import PluginPackageMetadata
from mne_nodes.backend.settings import Settings
from mne_nodes.gui.gui_theme import set_app_font_size, set_app_theme
from mne_nodes.gui.gui_utils import mouseMove, mousePress, mouseRelease

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "docs" / "screenshots" / "screenshots.toml"
DEFAULT_OUTPUT = ROOT / "docs" / "source" / "_static" / "screenshots" / "linux"
BUTTONS = {
    "left": Qt.MouseButton.LeftButton,
    "right": Qt.MouseButton.RightButton,
    "middle": Qt.MouseButton.MiddleButton,
}
# Allowed options per step action; the action key itself holds the target.
ACTIONS = {
    "call": {"args", "kwargs", "store"},
    "create": {"args", "kwargs", "store"},
    "set": {"value"},
    "click": {"item", "button", "double"},
    "hover": {"item"},
    "drag": {"to", "by", "offset", "button", "release", "moves"},
    "select": {"item"},
    "type": {"text"},
    "key": {"target"},
    "resize": {"size", "width", "height"},
    "wait": set(),
    "run": {"timeout"},
    "recipe": {"kwargs"},
}
HIGHLIGHT_KEYS = {
    "target",
    "item",
    "rect",
    "text",
    "color",
    "text_color",
    "fill",
    "width",
    "padding",
    "position",
}
SCREENSHOT_KEYS = {"name", "capture", "size", "window_size", "steps", "highlights"}
RECIPES: dict[str, Callable[..., Any]] = {}


class ScreenshotError(RuntimeError):
    """A scenario could not be configured, performed or captured."""


def recipe(func: Callable[..., Any]) -> Callable[..., Any]:
    """Register a Python helper for states that TOML steps cannot express."""
    RECIPES[func.__name__] = func
    return func


def resolve_path(value: str | Path, base: Path) -> Path:
    """Resolve ``resource:`` paths and paths relative to the configuration."""
    value = str(value)
    if value.startswith("resource:"):
        resource = files("mne_nodes.resources") / value.removeprefix("resource:")
        return Path(str(resource))
    path = Path(value)
    return path if path.is_absolute() else base / path


def wait_until(condition: Callable[[], bool], timeout: float, message: str) -> None:
    """Process Qt events until ``condition`` is true or raise after timeout."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise ScreenshotError(message)
        QTest.qWait(50)


def find_item(view: QAbstractItemView, text: str):
    """Return the first model index in a view whose display text is ``text``."""
    model = view.model()
    matches = model.match(
        model.index(0, 0),
        Qt.ItemDataRole.DisplayRole,
        text,
        1,
        Qt.MatchFlag.MatchExactly | Qt.MatchFlag.MatchRecursive,
    )
    if not matches:
        raise ScreenshotError(f"No item '{text}' in {type(view).__name__}.")
    return matches[0]


def item_rect(view: QAbstractItemView, text: str) -> QRectF:
    """Return the viewport rectangle of the whole row containing ``text``."""
    index = find_item(view, text)
    view.scrollTo(index)
    rect = QRectF(view.visualRect(index))
    for column in range(view.model().columnCount(index.parent())):
        sibling = QRectF(view.visualRect(index.siblingAtColumn(column)))
        if not sibling.isEmpty():
            rect = rect.united(sibling)
    return rect


class Scenario:
    """A disposable project in which the steps of one screenshot are performed.

    Parameters
    ----------
    project : dict
        The ``[project]`` table of the configuration.
    shot : dict
        The ``[[screenshots]]`` entry to perform.
    base : Path
        Directory of the configuration file for relative paths.
    workdir : Path
        Temporary directory for settings, data and generated files.
    """

    def __init__(self, project: dict, shot: dict, base: Path, workdir: Path):
        self.project = project
        self.shot = shot
        self.base = base
        self.workdir = workdir
        self.aliases: dict[str, Any] = {}
        self.window = None
        self.controller = None

    # ------------------------------------------------------------------
    # Project setup
    # ------------------------------------------------------------------
    def setup(self) -> None:
        """Create the project, its window and the configured node graph."""
        from mne_nodes.gui.main_window import MainWindow

        project = self.project
        os.environ["MNENODES_SETTINGS_DIR"] = str(self.workdir / "settings")
        settings = Settings()
        settings.set("first_start", False)
        settings.set("app_theme", project.get("theme", "light"))
        settings.set("keep_plots_open", False)
        settings.set("log_file_path", self.workdir / "mne_nodes.log")
        bids_root = self.workdir / "bids"
        copytree(resolve_path(project["dataset"], self.base), bids_root)
        settings.set("bids_root", bids_root)
        set_app_theme()
        set_app_font_size(project.get("font_size", 12))
        pipeline = self.workdir / "pipeline.json"
        config = {**default_config, "name": project.get("name", "Documentation")}
        pipeline.write_text(json.dumps(config), encoding="utf-8")
        self.controller = Controller(config_path=pipeline, settings=settings)
        for plugin in project.get("plugins", []):
            self.controller.load_plugin_path(resolve_path(plugin, self.base))
        for spec in project.get("imports", []):
            self._import_functions(spec)
        for datatype, patterns in project.get("inputs", {}).items():
            items = self.controller.get_datatype_items(datatype)
            selected = [i for i in items if any(fnmatch(i, p) for p in patterns)]
            if not selected:
                raise ScreenshotError(f"No {datatype} recordings match {patterns}.")
            self.controller.input_selection_changed(selected, data_type=datatype)
        self.window = MainWindow(self.controller)
        size = self.shot.get("window_size", project.get("window_size", [1800, 900]))
        self.window.setFixedSize(*size)
        self.window.menuBar().setNativeMenuBar(False)
        self.window.finalize_controller_setup()
        self._build_nodes()
        QTest.qWaitForWindowExposed(self.window)
        # Embedded node widgets resize once shown, which re-runs the auto-layout.
        QTest.qWait(200)
        viewer = self.window.viewer
        viewer.zoom_to_nodes()
        viewer.ensure_visible(viewer._combined_rect(viewer.nodes.values()))

    def _import_functions(self, spec: dict) -> None:
        from mne_nodes.gui.function_widgets import FunctionImporter

        plugin = spec["plugin_name"]
        importer = FunctionImporter(
            code=resolve_path(spec["file"], self.base).read_text(encoding="utf-8"),
            plugin_name=plugin,
            destination_dir=self.workdir,
            on_saved=self.controller.load_plugin_path,
            package_metadata=PluginPackageMetadata(
                distribution_name=f"mne-nodes_{plugin.replace('_', '-')}",
                description=spec.get("description", "Documentation functions"),
                author="mne-nodes contributors",
                license_expression="BSD-3-Clause",
            ),
        )
        if not importer.save():
            raise ScreenshotError(f"Could not import functions from {spec['file']}.")
        importer.deleteLater()

    def _build_nodes(self) -> None:
        viewer = self.window.viewer
        for spec in self.project.get("nodes", []):
            node = viewer.add_function_node(spec["function"])
            for name, value in spec.get("parameters", {}).items():
                node.parameter_guis[name].value = self.value(value)
            if "position" in spec:
                node.setPos(*spec["position"])
        for connection in self.project.get("connections", []):
            source, _, destination = (p.strip() for p in connection.partition("->"))
            self.port("output", source).connect_to(self.port("input", destination))
        if self.project.get("auto_layout", True):
            viewer.auto_layout_nodes()

    def close(self) -> None:
        """Close all windows created by the scenario."""
        for value in self.aliases.values():
            if isinstance(value, QWidget) and value.isWindow():
                value.close()
                value.deleteLater()
        if self.window is not None:
            for process in self.window.console_dock.processes:
                try:
                    process.kill()
                    process.waitForFinished(5000)
                except RuntimeError:
                    pass
            self.window.close()
            self.window.deleteLater()
        QTest.qWait(50)

    # ------------------------------------------------------------------
    # Target resolution
    # ------------------------------------------------------------------
    def node(self, name: str):
        """Return the input node for ``input`` or a function node by name."""
        viewer = self.window.viewer
        if name == "input":
            return viewer.input_node
        if name not in viewer.function_nodes:
            raise ScreenshotError(f"No node '{name}' in the project.")
        return viewer.function_nodes[name]

    def port(self, direction: str, reference: str):
        """Return the ``input``/``output`` port referenced by ``node.port``."""
        node_name, _, port_name = reference.partition(".")
        port = getattr(self.node(node_name), direction)(port_name=port_name)
        if port is None:
            raise ScreenshotError(f"No {direction} port '{reference}'.")
        return port

    def roots(self) -> dict[str, Any]:
        """Return the named objects that target paths may start with."""
        return {
            "app": QApplication.instance(),
            "window": self.window,
            "controller": self.controller,
            "viewer": self.window.viewer,
            **self.aliases,
        }

    def resolve(self, path: str) -> Any:
        """Resolve a target path such as ``window.console_dock``.

        Paths may start with ``node:<name>``, ``input:<node>.<port>`` or
        ``output:<node>.<port>`` to address node-graph items. Each further
        dot-separated segment is looked up as mapping key, attribute, list
        index, Qt object name or the text of a child widget. A segment ending
        with ``()`` calls the resolved method without arguments.
        """
        kind, separator, rest = path.partition(":")
        if separator and kind in ("node", "input", "output"):
            parts = rest.split(".")
            if kind == "node":
                obj, segments = self.node(parts[0]), parts[1:]
            else:
                obj = self.port(kind, ".".join(parts[:2]))
                segments = parts[2:]
        else:
            head, *segments = path.split(".")
            roots = self.roots()
            if head in roots:
                obj = roots[head]
            else:
                from mne_nodes.gui.widget_registry import get_widget

                obj = get_widget(head)
                if obj is None:
                    raise ScreenshotError(f"Unknown target root '{head}' in '{path}'.")
        for segment in segments:
            obj = self._child(obj, segment, path)
        return obj

    @staticmethod
    def _child(obj: Any, segment: str, path: str) -> Any:
        call = segment.endswith("()")
        name = segment.removesuffix("()")
        if isinstance(obj, Mapping) and name in obj:
            value = obj[name]
        elif hasattr(obj, name):
            value = getattr(obj, name)
        elif isinstance(obj, list | tuple) and name.lstrip("-").isdigit():
            value = obj[int(name)]
        elif isinstance(obj, QObject) and obj.findChild(QObject, name) is not None:
            value = obj.findChild(QObject, name)
        else:
            value = next(
                (
                    child
                    for child in (
                        obj.findChildren(QWidget) if isinstance(obj, QWidget) else []
                    )
                    if callable(getattr(child, "text", None))
                    and child.text().replace("&", "") == name
                ),
                None,
            )
            if value is None:
                raise ScreenshotError(f"Cannot resolve '{name}' in '{path}'.")
        return value() if call else value

    def value(self, value: Any) -> Any:
        """Resolve ``@target`` references and ``path:``/``resource:`` paths."""
        if isinstance(value, str):
            if value.startswith("@@"):
                return value[1:]
            if value.startswith("@"):
                return self.resolve(value[1:])
            if value.startswith("path:"):
                return resolve_path(value.removeprefix("path:"), self.base)
            if value.startswith("resource:"):
                return resolve_path(value, self.base)
            return value
        if isinstance(value, list):
            return [self.value(item) for item in value]
        if isinstance(value, dict):
            return {key: self.value(item) for key, item in value.items()}
        return value

    def event_position(self, obj: Any, item: str | None = None):
        """Return the widget receiving mouse events and the local position."""
        if isinstance(obj, QGraphicsItem):
            view = obj.scene().views()[0]
            position = view.mapFromScene(obj.sceneBoundingRect().center())
            return view.viewport(), position
        if not isinstance(obj, QWidget):
            raise ScreenshotError(f"{obj!r} is neither a widget nor a graph item.")
        if item is not None:
            if not isinstance(obj, QAbstractItemView):
                raise ScreenshotError("'item' requires an item view target.")
            rect = obj.visualRect(find_item(obj, item))
            return obj.viewport(), rect.center()
        if isinstance(obj, QAbstractScrollArea):
            return obj.viewport(), obj.viewport().rect().center()
        return obj, obj.rect().center()

    def global_rect(self, obj: Any, item: str | None = None) -> QRectF:
        """Return the screen rectangle of a widget, view item or graph item."""
        if isinstance(obj, QGraphicsItem):
            view = obj.scene().views()[0]
            rect = view.mapFromScene(obj.sceneBoundingRect()).boundingRect()
            widget = view.viewport()
        elif isinstance(obj, QWidget) and item is not None:
            if not isinstance(obj, QAbstractItemView):
                raise ScreenshotError("'item' requires an item view target.")
            rect = item_rect(obj, item).toRect()
            widget = obj.viewport()
        elif isinstance(obj, QWidget):
            rect, widget = obj.rect(), obj
        else:
            raise ScreenshotError(f"Cannot highlight {obj!r}.")
        top_left = widget.mapToGlobal(rect.topLeft())
        return QRectF(QPointF(top_left), QSizeF(rect.size()))

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def run_step(self, step: dict) -> None:
        """Perform a single configured step."""
        actions = [action for action in ACTIONS if action in step]
        if len(actions) != 1:
            raise ScreenshotError(
                f"Each step needs exactly one action of {sorted(ACTIONS)}: {step}"
            )
        action = actions[0]
        unknown = set(step) - ACTIONS[action] - {action}
        if unknown:
            raise ScreenshotError(f"Unknown options {sorted(unknown)} for '{action}'.")
        getattr(self, f"_{action}")(step[action], step)
        QTest.qWait(20)

    def _call(self, target: str, step: dict) -> None:
        result = self.resolve(target)(
            *self.value(step.get("args", [])), **self.value(step.get("kwargs", {}))
        )
        if "store" in step:
            self.aliases[step["store"]] = result

    def _create(self, class_path: str, step: dict) -> None:
        module, _, name = class_path.rpartition(".")
        cls = getattr(importlib.import_module(module), name)
        if "store" not in step:
            raise ScreenshotError(f"'create' of {class_path} requires 'store'.")
        self.aliases[step["store"]] = cls(
            *self.value(step.get("args", [])), **self.value(step.get("kwargs", {}))
        )

    def _set(self, target: str, step: dict) -> None:
        owner_path, _, name = target.rpartition(".")
        owner = self.resolve(owner_path)
        value = self.value(step["value"])
        setter = getattr(owner, f"set{name[:1].upper()}{name[1:]}", None)
        if isinstance(owner, dict):
            owner[name] = value
        elif callable(getattr(owner, name, None)) and callable(setter):
            setter(value)
        else:
            setattr(owner, name, value)

    def _click(self, target: str, step: dict) -> None:
        widget, position = self.event_position(self.resolve(target), step.get("item"))
        button = BUTTONS[step.get("button", "left")]
        mouseMove(widget=widget, pos=position)
        if step.get("double", False):
            QTest.mouseDClick(widget, button, pos=position)
        else:
            mousePress(widget=widget, pos=position, button=button)
            mouseRelease(widget=widget, pos=position, button=button)

    def _hover(self, target: str, step: dict) -> None:
        widget, position = self.event_position(self.resolve(target), step.get("item"))
        mouseMove(widget=widget, pos=position)

    def _drag(self, target: str, step: dict) -> None:
        widget, start = self.event_position(self.resolve(target))
        if "to" in step:
            end_widget, end = self.event_position(self.resolve(step["to"]))
            end = widget.mapFromGlobal(end_widget.mapToGlobal(end))
        elif "by" in step:
            end = start + QPoint(*step["by"])
        else:
            raise ScreenshotError("'drag' requires 'to' or 'by'.")
        end += QPoint(*step.get("offset", [0, 0]))
        button = BUTTONS[step.get("button", "left")]
        mouseMove(widget=widget, pos=start)
        mousePress(widget=widget, pos=start, button=button)
        moves = max(1, step.get("moves", 10))
        for index in range(1, moves + 1):
            position = start + (end - start) * (index / moves)
            mouseMove(widget=widget, pos=position, button=button)
        if step.get("release", True):
            mouseRelease(widget=widget, pos=end, button=button)

    def _select(self, target: str, step: dict) -> None:
        obj = self.resolve(target)
        item = step.get("item")
        if isinstance(obj, QGraphicsItem):
            obj.setSelected(True)
        elif isinstance(obj, QAbstractItemView):
            index = find_item(obj, item)
            obj.setCurrentIndex(index)
            obj.scrollTo(index)
        elif isinstance(obj, QComboBox):
            if obj.findText(item) < 0:
                raise ScreenshotError(f"No combo-box entry '{item}' in '{target}'.")
            obj.setCurrentText(item)
        elif isinstance(obj, QTabWidget):
            texts = [obj.tabText(i).replace("&", "") for i in range(obj.count())]
            if item not in texts:
                raise ScreenshotError(f"No tab '{item}' in '{target}'.")
            obj.setCurrentIndex(texts.index(item))
        else:
            raise ScreenshotError(f"Cannot select in {type(obj).__name__}.")

    def _type(self, target: str, step: dict) -> None:
        widget = self.resolve(target)
        widget.setFocus()
        QTest.keyClicks(widget, step["text"])

    def _key(self, sequence: str, step: dict) -> None:
        combination = QKeySequence(sequence)[0]
        widget = (
            self.resolve(step["target"])
            if "target" in step
            else QApplication.focusWidget() or self.window
        )
        QTest.keyClick(widget, combination.key(), combination.keyboardModifiers())

    def _resize(self, target: str, step: dict) -> None:
        widget = self.resolve(target)
        if "size" in step:
            widget.setFixedSize(*step["size"])
        if "width" in step:
            widget.setFixedWidth(step["width"])
        if "height" in step:
            widget.setFixedHeight(step["height"])

    def _wait(self, milliseconds: int, step: dict) -> None:
        QTest.qWait(milliseconds)

    def _run(self, nodes: list[str], step: dict) -> None:
        self.controller.ensure_deriv_root(interactive=False)
        self.controller.ensure_subjects_dir(interactive=False)
        self.controller.flush()
        dock = self.window.console_dock
        count = len(dock.processes)
        self.window.viewer.start_nodes([self.node(name) for name in nodes])
        if len(dock.processes) == count:
            raise ScreenshotError(f"Starting {nodes} did not start a process.")
        process = dock.processes[-1]
        console = process.console
        result = []
        process.allFinished.connect(lambda code, status: result.append(code))
        timeout = step.get("timeout", 120)
        wait_until(lambda: bool(result), timeout, f"{nodes} ran over {timeout} s.")
        if result[0] != 0:
            raise ScreenshotError(f"Pipeline failed:\n{console.toPlainText()}")
        wait_until(
            lambda: "Pipeline finished." in console.toPlainText(),
            10,
            "The console did not show the finished pipeline.",
        )

    def _recipe(self, name: str, step: dict) -> None:
        if name not in RECIPES:
            raise ScreenshotError(f"Unknown recipe '{name}', use {sorted(RECIPES)}.")
        RECIPES[name](self, **self.value(step.get("kwargs", {})))

    # ------------------------------------------------------------------
    # Capture
    # ------------------------------------------------------------------
    def capture(self) -> QImage:
        """Grab the capture target at logical size and draw highlights."""
        widget = self.resolve(self.shot.get("capture", "window"))
        if not isinstance(widget, QWidget):
            raise ScreenshotError(f"Capture target {widget!r} is not a widget.")
        if "size" in self.shot:
            if not widget.isWindow():
                raise ScreenshotError(
                    "'size' only applies to windows; use 'window_size' or a "
                    "'resize' step for child widgets."
                )
            widget.setFixedSize(*self.shot["size"])
        if not widget.isVisible():
            widget.show()
        QTest.qWaitForWindowExposed(widget.window())
        wait_until(lambda: widget.width() > 0, 10, "Capture target has no size.")
        QTest.qWait(200)
        size = [widget.width(), widget.height()]
        if "size" in self.shot and size != self.shot["size"]:
            raise ScreenshotError(f"Capture has size {size}, not {self.shot['size']}.")
        widget.repaint()
        image = widget.grab().toImage()
        if image.isNull():
            raise ScreenshotError("Qt returned an empty capture.")
        image = image.scaled(
            widget.size(),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        image.setDevicePixelRatio(1)
        highlights = self.shot.get("highlights", [])
        if highlights:
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            for spec in highlights:
                draw_highlight(painter, self.highlight_rect(spec, widget), spec)
            painter.end()
        return image

    def highlight_rect(self, spec: dict, widget: QWidget) -> QRectF:
        """Return the highlight rectangle in capture coordinates."""
        unknown = set(spec) - HIGHLIGHT_KEYS
        if unknown:
            raise ScreenshotError(f"Unknown highlight options {sorted(unknown)}.")
        if "rect" in spec:
            return QRectF(*spec["rect"])
        if "target" not in spec:
            raise ScreenshotError("A highlight needs 'target' or 'rect'.")
        rect = self.global_rect(self.resolve(spec["target"]), spec.get("item"))
        top_left = widget.mapFromGlobal(rect.topLeft().toPoint())
        return QRectF(QPointF(top_left), rect.size())


def draw_highlight(painter: QPainter, rect: QRectF, spec: dict) -> None:
    """Draw a rounded highlight rectangle with an optional text label."""
    bounds = QRectF(painter.device().rect())
    color = QColor(spec.get("color", "#e53935"))
    padding = spec.get("padding", 6)
    rect = rect.adjusted(-padding, -padding, padding, padding)
    if "fill" in spec:
        painter.fillRect(rect, QColor(spec["fill"]))
    painter.setPen(QPen(color, spec.get("width", 3)))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(rect, 6, 6)
    text = spec.get("text")
    if not text:
        return
    font = QApplication.font()
    font.setBold(True)
    font.setPointSizeF(font.pointSizeF() + 1)
    painter.setFont(font)
    margin, gap = 8.0, 6.0
    flags = Qt.TextFlag.TextWordWrap
    max_width = min(420.0, bounds.width() - 2 * margin)
    text_rect = QFontMetricsF(font).boundingRect(
        QRectF(0, 0, max_width, bounds.height()), flags, text
    )
    box = QRectF(0, 0, text_rect.width() + 2 * margin, text_rect.height() + margin)
    position = spec.get("position", "bottom")
    above = rect.top() - gap - box.height()
    below = rect.bottom() + gap
    left = rect.left() - gap - box.width()
    right = rect.right() + gap
    # Flip to the opposite side if the label does not fit into the image.
    if position == "bottom":
        fits = below + box.height() <= bounds.bottom()
        box.moveTo(rect.left(), below if fits else above)
    elif position == "top":
        box.moveTo(rect.left(), above if above >= bounds.top() else below)
    elif position == "right":
        fits = right + box.width() <= bounds.right()
        box.moveTo(right if fits else left, rect.top())
    elif position == "left":
        box.moveTo(left if left >= bounds.left() else right, rect.top())
    elif position == "inside":
        box.moveTo(rect.left() + gap, rect.top() + gap)
    else:
        raise ScreenshotError(f"Unknown highlight position '{position}'.")
    box.moveLeft(min(max(box.left(), bounds.left()), bounds.right() - box.width()))
    box.moveTop(min(max(box.top(), bounds.top()), bounds.bottom() - box.height()))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(box, 5, 5)
    painter.setPen(QColor(spec.get("text_color", "#ffffff")))
    text_box = box.adjusted(margin, margin / 2, -margin, -margin / 2)
    painter.drawText(text_box, flags, text)


@recipe
def synthetic_coregistration(scenario: Scenario, dialog) -> None:
    """Populate a CoregDialog with two synthetic recordings and a transform."""
    import mne
    from mne_bids import BIDSPath

    from mne_nodes.backend.coregistration import CoregGroup, CoregRecording

    info = mne.create_info(["EEG001"], 100, "eeg")
    info.set_montage(
        mne.channels.make_dig_montage(
            ch_pos={"EEG001": [0.0, 0.0, 0.09]},
            nasion=[0.0, 0.1, 0.0],
            lpa=[-0.08, 0.0, 0.0],
            rpa=[0.08, 0.0, 0.0],
            coord_frame="head",
        )
    )
    recordings = [
        CoregRecording(
            BIDSPath(
                root=scenario.workdir / "bids",
                subject="01",
                session="01",
                task="demo",
                run=run,
                datatype="eeg",
                suffix="eeg",
                extension=".fif",
                check=False,
            ),
            info.copy(),
        )
        for run in ("01", "02")
    ]
    trans = scenario.workdir / "demo_trans.fif"
    mne.write_trans(trans, mne.transforms.Transform("head", "mri"))
    recordings[0].existing_trans = trans
    dialog.mri_subject.addItems(["", "sub-01"])
    dialog._discovered([CoregGroup(recordings)])
    dialog.recording_list.view.setCurrentIndex(dialog.recording_list.model.index(0, 0))


def load_config(path: Path) -> dict:
    """Load and minimally validate a screenshot configuration file."""
    with path.open("rb") as file:
        config = tomllib.load(file)
    if "project" not in config or "dataset" not in config["project"]:
        raise ScreenshotError(f"{path} needs a [project] table with 'dataset'.")
    names = [shot.get("name") for shot in config.get("screenshots", [])]
    if None in names or len(set(names)) != len(names):
        raise ScreenshotError("Every [[screenshots]] entry needs a unique 'name'.")
    for shot in config.get("screenshots", []):
        unknown = set(shot) - SCREENSHOT_KEYS
        if unknown:
            raise ScreenshotError(f"Unknown keys {sorted(unknown)} in {shot['name']}.")
    return config


def _script_folder(controller: Controller) -> Path:
    folder = Path(controller.config_path).parent / "scripts"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def take_screenshot(config: dict, shot: dict, base: Path, output: Path) -> Path:
    """Perform one screenshot in a fresh project and save it as PNG."""
    workdir = TemporaryDirectory(prefix="mne-nodes-docs-", ignore_cleanup_errors=True)
    with workdir as tmp:
        scenario = Scenario(config["project"], shot, base, Path(tmp))
        try:
            scenario.setup()
            for step in shot.get("steps", []):
                scenario.run_step(step)
            image = scenario.capture()
        finally:
            scenario.close()
    path = output / f"{shot['name']}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not image.save(str(path), "PNG") or QImage(str(path)).isNull():
        raise ScreenshotError(f"Could not save screenshot: {path}")
    return path


def main(argv: list[str] | None = None) -> int:
    """Generate the configured documentation screenshots."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("names", nargs="*", help="Screenshots to take (default: all)")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(os.environ.get("MNENODES_SCREENSHOT_DIR", DEFAULT_OUTPUT)),
    )
    parser.add_argument("--list", action="store_true", help="List screenshot names")
    args = parser.parse_args(argv)
    config_path = args.config.resolve()
    config = load_config(config_path)
    shots = config.get("screenshots", [])
    if args.list:
        print("\n".join(shot["name"] for shot in shots))
        return 0
    missing = set(args.names) - {shot["name"] for shot in shots}
    if missing:
        parser.error(f"Unknown screenshots: {', '.join(sorted(missing))}")
    selected = [s for s in shots if not args.names or s["name"] in args.names]

    os.environ["MNENODES_DEBUG"] = "false"
    mne_nodes.gui_mode = False
    # Only the configured plugins are shown and generated scripts stay temporary.
    controller_module.get_plugin_entry_points = list
    Controller.run_script_folder = property(_script_folder)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("mne-nodes")
    failures = 0
    for shot in selected:
        try:
            path = take_screenshot(config, shot, config_path.parent, args.output)
        except Exception:  # noqa: BLE001
            # Report every failing scenario instead of stopping at the first.
            failures += 1
            print(f"FAILED {shot['name']}:", file=sys.stderr)
            traceback.print_exc()
        else:
            print(f"Saved {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
