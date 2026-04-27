"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
from datetime import datetime
import multiprocessing
import os
from queue import Empty

import numpy as np
import pytest

from mne_nodes.pipeline.io import TypedJSONEncoder, type_json_hook
from mne_nodes.pipeline.settings import Settings


def test_json_serialization(parameter_values):
    """Test if JSON serialization works as expected."""
    # Add nested dict with possible extra types
    # ToDo: Add ParameterGuis for array (nested TableView) and datetime
    parameter_values.update(
        {
            "array": np.array([[1, 2, 3], [4, 5, 6]]),
            "datetime": datetime(2000, 1, 1, 12, 0, 0),
        }
    )
    serialized = json.dumps(parameter_values, indent=4, cls=TypedJSONEncoder)
    deserialized = json.loads(serialized, object_hook=type_json_hook)
    # Check if the deserialized values match the original ones
    for key, value in parameter_values.items():
        assert key in deserialized, f"Key {key} not found in deserialized JSON"
        if isinstance(value, np.ndarray):
            np.testing.assert_allclose(deserialized[key], value)
        else:
            assert deserialized[key] == value, (
                f"Value mismatch for key {key}: {deserialized[key]} != {value}"
            )
        # Check if the type is preserved
        assert isinstance(deserialized[key], type(value)), (
            f"Type mismatch for key {key}"
        )


def test_settings(parameter_values):
    """Test if (Q)Settings work as expected.

    qtbot is needed to initialize the QApplication.
    """
    settings = Settings()
    for k, v in parameter_values.items():
        if k not in ["int", "float", "string", "bool", "tuple", "path"]:
            continue
        settings.set(k, v)
        value = settings.get(k)
        # Check if the value is set correctly
        assert value == v, f"Expected {v} for key {k}, got {value}"
        # Check if the type is preserved
        assert isinstance(value, type(parameter_values[k])), (
            f"Type mismatch for key {k}"
        )
        # Check if unsupported types raise an error (e.g. for dicts)
        with pytest.raises(TypeError):
            settings.set("unsupported_type", Settings)
        # Check, if None is handled correctly
        settings.set("none_type", None)
        assert settings.get("none_type") is None, "Expected None for 'none_type' key"


def _settings_worker(
    settings_dir: str, key: str, values: list[int], result_queue: multiprocessing.Queue
) -> None:
    os.environ["MNENODES_SETTINGS_DIR"] = settings_dir
    settings = Settings()
    try:
        for value in values:
            settings.set(key, value)
            if settings.get(key) != value:
                raise AssertionError(f"Expected {value} for {key} in worker")
        result_queue.put(("ok", key))
    except Exception as err:  # pragma: no cover - propagated via exit code
        result_queue.put(("error", key, repr(err)))
        raise


def test_settings_lock_multi_process(tmp_path, monkeypatch):
    settings_dir = tmp_path / "settings_lock"
    settings_dir.mkdir()
    monkeypatch.setenv("MNENODES_SETTINGS_DIR", str(settings_dir))

    ctx = multiprocessing.get_context("spawn")
    result_queue = ctx.Queue()
    payloads = {f"concurrent_key_{idx}": list(range(20)) for idx in range(4)}

    processes = []
    for idx, (key, values) in enumerate(payloads.items()):
        proc = ctx.Process(
            target=_settings_worker,
            name=f"settings-writer-{idx}",
            args=(str(settings_dir), key, values, result_queue),
        )
        proc.start()
        processes.append(proc)

    for _ in processes:
        try:
            status = result_queue.get(timeout=30)
        except Empty:  # pragma: no cover - indicates a hung worker
            pytest.fail("Worker process did not report completion")
        if status[0] != "ok":
            pytest.fail(f"Worker {status[1]} failed with {status[2]}")

    for proc in processes:
        proc.join(timeout=30)
        assert proc.exitcode == 0, f"Worker {proc.name} exited with {proc.exitcode}"

    settings_path = settings_dir / "settings.json"
    assert settings_path.exists(), "Settings file missing after concurrent writes"
    with settings_path.open("r", encoding="utf-8") as handle:
        stored_settings = json.load(handle)

    for key, values in payloads.items():
        assert stored_settings[key] == values[-1], (
            f"Expected final value {values[-1]} for {key}, got {stored_settings.get(key)}"
        )
