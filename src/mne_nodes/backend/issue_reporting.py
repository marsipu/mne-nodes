"""Privacy-conscious diagnostics for user-reviewed error reports."""

import getpass
import re
import socket
from importlib.metadata import version
from io import StringIO
from pathlib import Path
from typing import TYPE_CHECKING

import mne

if TYPE_CHECKING:
    from mne_nodes.backend.controller import Controller


def anonymize_report(text: str) -> str:
    """Remove local identities, paths, addresses and URLs from report text.

    Free-form exception messages can still contain private information and must
    be reviewed by the user before sharing.
    """
    try:
        return _anonymize_report(text)
    except Exception as error:  # noqa: BLE001
        return (
            f"Report redaction failed ({type(error).__name__}). "
            "Original text omitted to protect private information."
        )


def _anonymize_report(text: str) -> str:
    text = re.sub(r"https?://[^\s\"'<>]+", "[url]", text)
    text = re.sub(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[email]", text)
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[address]", text)
    identities = {str(Path.home()), socket.gethostname()}
    identities.add(getpass.getuser())
    for identity in sorted(identities, key=len, reverse=True):
        if identity:
            text = re.sub(
                rf"(?<!\w){re.escape(identity)}(?!\w)",
                "[redacted]",
                text,
                flags=re.IGNORECASE,
            )
    # Include spaces in quoted paths (e.g. traceback filenames).
    text = re.sub(r"""(["'])(?:[A-Za-z]:[\\/]|\\\\|/|~/).*?\1""", '"[path]"', text)
    text = re.sub(
        r"""(?<![\w:])(?:[A-Za-z]:[\\/]|\\\\|/|~/)[^\n"'<>]*""", "[path]", text
    )
    return text


def collect_diagnostics(controller: "Controller | None" = None) -> str:
    """Collect system info and a minimal in-memory plugin/dataset summary."""
    sections = []
    try:
        output = StringIO()
        mne.sys_info(fid=output, check_version=False)
        sections.append(f"mne-nodes: {version('mne-nodes')}\n{output.getvalue()}")
    except Exception as error:  # noqa: BLE001
        # Diagnostics must not obscure the original error.
        sections.append(f"System information unavailable ({type(error).__name__}).")

    if controller is None:
        sections.append("Plugins and dataset: unavailable (no active pipeline).")
    else:
        try:
            config = controller._config
            metadata = config.get("plugin_meta", {})
            plugins = []
            for index, (name, module) in enumerate(controller.plugins.items(), 1):
                plugin_type = metadata.get(name, {}).get("plugin_type")
                label = name if plugin_type == "module" else f"custom plugin {index}"
                plugin_version = getattr(module, "__version__", "unknown version")
                plugins.append(f"- {label}: {plugin_version}")
            sections.append("Loaded plugins:\n" + ("\n".join(plugins) or "None"))
            selected = config.get("selected_inputs", {})
            counts = [
                f"- {datatype}: {len(selected[datatype])}"
                for datatype in controller.raw_datatypes
                if datatype in selected
            ]
            sections.append(
                "Dataset selection counts (names and identifiers omitted):\n"
                + ("\n".join(counts) or "No selected inputs")
            )
        except Exception as error:  # noqa: BLE001
            sections.append(
                f"Pipeline information unavailable ({type(error).__name__})."
            )
    return anonymize_report("\n\n".join(sections))
