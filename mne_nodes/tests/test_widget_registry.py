"""Tests for application-scoped widget lookup and lifetime management."""

import gc
from weakref import ref

import pytest
from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtWidgets import QApplication, QWidget

from mne_nodes.gui.widget_registry import WidgetRegistry, get_widget, widget_registry


def test_lookup_before_application(monkeypatch):
    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    assert get_widget("main_window") is None
    with pytest.raises(RuntimeError, match="requires a QApplication"):
        widget_registry()


def test_application_registry(qapp):
    registry = widget_registry()
    widget = QWidget()
    registry.register("registry_test", widget)
    assert widget_registry() is registry
    assert get_widget("registry_test") is widget
    registry.unregister("registry_test", widget)
    assert get_widget("registry_test") is None


def test_discovery_does_not_retain_widget(qapp):
    registry = WidgetRegistry()
    widget = QWidget()
    reference = ref(widget)
    registry.register("widget", widget)
    del widget
    gc.collect()
    assert reference() is None
    assert registry.get("widget") is None


def test_explicit_retention(qapp):
    registry = WidgetRegistry()
    widget = QWidget()
    reference = ref(widget)
    registry.register("widget", widget, retain=True)
    del widget
    gc.collect()
    assert registry.get("widget") is reference()
    assert reference() is not None
    registry.unregister("widget")
    gc.collect()
    assert reference() is None


def test_destroyed_widget_is_removed(qapp):
    registry = WidgetRegistry()
    widget = QWidget()
    registry.register("widget", widget, retain=True)
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert registry.get("widget") is None


def test_old_widget_cannot_unregister_replacement(qapp):
    registry = WidgetRegistry()
    old_widget = QWidget()
    replacement = QWidget()
    registry.register("widget", old_widget)
    registry.register("widget", replacement)
    registry.unregister("widget", old_widget)
    assert registry.get("widget") is replacement
    old_widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert registry.get("widget") is replacement
