"""Tests for application-scoped widget lookup and lifetime management."""

import gc
from weakref import ref

import pytest
from qtpy.QtCore import QCoreApplication, QEvent
from qtpy.QtWidgets import QApplication, QWidget

from mne_nodes.gui.widget_registry import WidgetRegistry, get_widget, widget_registry


def test_application_registry_lookup(qapp, monkeypatch):
    """The global registry is application-scoped and unavailable without one."""
    registry = widget_registry()
    widget = QWidget()
    registry.register("registry_test", widget)
    assert widget_registry() is registry
    assert get_widget("registry_test") is widget
    registry.unregister("registry_test", widget)
    assert get_widget("registry_test") is None

    monkeypatch.setattr(QApplication, "instance", staticmethod(lambda: None))
    assert get_widget("main_window") is None
    with pytest.raises(RuntimeError, match="requires a QApplication"):
        widget_registry()


def test_registry_widget_lifetime(qapp):
    """Weak/retained references, deletion and replacement are handled safely."""
    registry = WidgetRegistry()
    widget = QWidget()
    reference = ref(widget)
    registry.register("weak", widget)
    del widget
    gc.collect()
    assert reference() is None
    assert registry.get("weak") is None

    widget = QWidget()
    reference = ref(widget)
    registry.register("retained", widget, retain=True)
    del widget
    gc.collect()
    assert registry.get("retained") is reference()
    assert reference() is not None
    registry.unregister("retained")
    gc.collect()
    assert reference() is None

    deleted = QWidget()
    registry.register("deleted", deleted, retain=True)
    deleted.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert registry.get("deleted") is None

    old_widget = QWidget()
    replacement = QWidget()
    registry.register("widget", old_widget)
    registry.register("widget", replacement)
    registry.unregister("widget", old_widget)
    assert registry.get("widget") is replacement
    old_widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert registry.get("widget") is replacement
