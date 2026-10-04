"""Application-scoped widget discovery and optional lifetime management."""

from weakref import ReferenceType, ref

from qtpy.QtWidgets import QApplication, QWidget


class WidgetRegistry:
    """Discover widgets without owning them unless retention is requested."""

    def __init__(self) -> None:
        self._references: dict[str, ReferenceType[QWidget]] = {}
        self._retained: dict[str, QWidget] = {}

    def register(self, name: str, widget: QWidget, *, retain: bool = False) -> None:
        """Register a widget and optionally keep its Python wrapper alive."""
        if not isinstance(widget, QWidget):
            raise TypeError("Only QWidget instances can be registered.")
        self.unregister(name)
        reference = ref(widget, lambda reference: self._discard(name, reference))
        self._references[name] = reference
        if retain:
            self._retained[name] = widget
        widget.destroyed.connect(lambda: self._discard(name, reference))

    def get(self, name: str) -> QWidget | None:
        """Return a registered widget, or None if it is unavailable."""
        reference = self._references.get(name)
        return reference() if reference is not None else None

    def unregister(self, name: str, widget: QWidget | None = None) -> None:
        """Remove an entry, optionally only if it still refers to widget."""
        reference = self._references.get(name)
        if reference is not None and (widget is None or reference() is widget):
            self._discard(name, reference)

    def _discard(self, name: str, reference: ReferenceType[QWidget]) -> None:
        if self._references.get(name) is reference:
            self._references.pop(name)
            self._retained.pop(name, None)


def widget_registry() -> WidgetRegistry:
    """Return the QApplication registry, creating it on first access."""
    app = QApplication.instance()
    if not isinstance(app, QApplication):
        raise TypeError("Widget registration requires a QApplication.")
    registry = getattr(app, "_mne_nodes_widget_registry", None)
    if registry is None:
        registry = WidgetRegistry()
        app._mne_nodes_widget_registry = registry
    return registry


def get_widget(name: str) -> QWidget | None:
    """Look up a widget, returning None before GUI initialization."""
    if not isinstance(QApplication.instance(), QApplication):
        return None
    return widget_registry().get(name)
