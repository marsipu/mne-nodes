import json
import logging
import subprocess
import sys
import textwrap

import pytest


def test_adding_all_mne_nodes(ct, tmp_path):
    all_functions = len(ct.function_meta)
    failed_functions = []
    batch_size = 50
    marker = "MNE_NODES_WORKER_RESULT="

    worker_code = textwrap.dedent(
        """
        import json
        import os
        import sys
        import traceback
        from pathlib import Path

        from qtpy.QtCore import QCoreApplication, QEvent
        from qtpy.QtWidgets import QApplication

        function_names = json.loads(sys.argv[1])
        settings_dir = Path(sys.argv[2])

        os.environ["MNENODES_DEBUG"] = "true"
        os.environ["MNENODES_SETTINGS_DIR"] = str(settings_dir)

        from mne_nodes.pipeline.settings import Settings
        from mne_nodes.pipeline.controller import Controller
        import mne_nodes.pipeline.controller as controller_module
        from mne_nodes.conftest import tiny_bids_root
        from mne_nodes.gui.node.nodes import FunctionNode

        def dummy_user_input(*args, **kwargs):
            input_type = kwargs.get("input_type")
            if input_type == "string":
                return "test"
            if input_type == "folder":
                return settings_dir
            raise RuntimeError(f"Unknown input type: {input_type}")

        controller_module.ask_user_custom = lambda *args, **kwargs: True
        controller_module.get_user_input = dummy_user_input
        controller_module.raise_user_attention = lambda *args, **kwargs: None

        settings = Settings()
        settings.set("bids_root", tiny_bids_root)
        ct = Controller(settings=settings)
        ct.ensure_ready(required=("config_path",))

        app = QApplication.instance() or QApplication([])
        failures = []

        for func_name in function_names:
            node = None
            try:
                node = FunctionNode(ct, name=func_name)
            except Exception as err:
                failures.append(
                    {
                        "function": func_name,
                        "error": f"{type(err).__name__}: {err}",
                        "traceback": traceback.format_exc(),
                    }
                )
            finally:
                if node is not None:
                    try:
                        node.delete()
                    except Exception as err:
                        failures.append(
                            {
                                "function": f"{func_name} (cleanup)",
                                "error": f"{type(err).__name__}: {err}",
                                "traceback": traceback.format_exc(),
                            }
                        )
                app.processEvents()
                QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
                app.processEvents()

        print("""
        + repr(marker)
        + """ + json.dumps(failures))
        """
    )

    def run_batch(function_batch):
        if not function_batch:
            return

        result = subprocess.run(
            [
                sys.executable,
                "-c",
                worker_code,
                json.dumps(function_batch),
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=str(tmp_path.parent),
            timeout=300,
        )

        if result.returncode != 0:
            if len(function_batch) == 1:
                func_name = function_batch[0]
                output = (
                    result.stderr or result.stdout
                ).strip() or "No output captured."
                failed_functions.append(
                    f"- {func_name}: process crashed (returncode={result.returncode})\n{output}"
                )
                return

            midpoint = len(function_batch) // 2
            run_batch(function_batch[:midpoint])
            run_batch(function_batch[midpoint:])
            return

        worker_line = None
        for line in (result.stdout or "").splitlines():
            if line.startswith(marker):
                worker_line = line

        if worker_line is None:
            details = (
                result.stdout or result.stderr or "No worker result found."
            ).strip()
            failed_functions.append(
                "- Batch result parsing failed:\n"
                f"Functions: {', '.join(function_batch)}\n"
                f"Output:\n{details}"
            )
            return

        try:
            worker_failures = json.loads(worker_line[len(marker) :])
        except Exception as err:
            failed_functions.append(
                f"- Batch JSON parse error ({type(err).__name__}: {err}) for functions: {', '.join(function_batch)}"
            )
            return

        for item in worker_failures:
            failed_functions.append(
                f"- {item['function']}: {item['error']}\n{item['traceback']}"
            )

    function_names = list(ct.function_meta)
    for start_idx in range(0, len(function_names), batch_size):
        run_batch(function_names[start_idx : start_idx + batch_size])

    logging.info(f"Tested {all_functions}/{all_functions} MNE functions.")

    if failed_functions:
        details = "\n".join(failed_functions)
        pytest.fail(
            f"{len(failed_functions)} function-node issues encountered:\n{details}"
        )
