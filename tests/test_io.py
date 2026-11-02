"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import json
import multiprocessing
import os
from datetime import UTC, date, datetime, time
from pathlib import Path
from queue import Empty

import numpy as np
import pandas as pd
import pytest

from mne_nodes.backend.io import (
    TypedJSONEncoder,
    date_format,
    datetime_format,
    load_json_progress,
    time_format,
    type_json_hook,
)
from mne_nodes.backend.settings import Settings


def test_json_serialization(parameter_values):
    """Test if JSON serialization works as expected."""
    # Add nested dict with possible extra types
    # ToDo: Add ParameterGui for array (nested TableView)
    parameter_values.update(
        {
            "array": np.array([[1, 2, 3], [4, 5, 6]]),
            "date": date(2000, 1, 1),
            "time": time(12, 30, 15),
        }
    )
    serialized = json.dumps(parameter_values, indent=4, cls=TypedJSONEncoder)
    deserialized = json.loads(serialized, object_hook=type_json_hook)
    # Check if the deserialized values match the original ones
    for key, value in parameter_values.items():
        assert key in deserialized, f"Key {key} not found in deserialized JSON"
        if isinstance(value, np.ndarray):
            np.testing.assert_allclose(deserialized[key], value)
        elif isinstance(value, pd.DataFrame):
            assert deserialized[key].equals(value), (
                f"Value mismatch for key {key}: {deserialized[key]} != {value}"
            )
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
        assert isinstance(value, type(v)), f"Type mismatch for key {k}"
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


def _assert_no_none_keys(value):
    if isinstance(value, dict):
        assert None not in value
        for nested in value.values():
            _assert_no_none_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _assert_no_none_keys(nested)


def test_load_json_progress(tmp_path):
    """Native JSON values (incl. nulls) and typed special values are restored."""
    native = {
        "int": 7,
        "float": 1.25,
        "string": "hello",
        "bool": True,
        "none": None,
        "list": [1, 2.5, "x", False, None],
        "parameters": {"plot_raw": {"scalings": None, "title": None}},
        "nested": [{"a": None}, {"b": [1, None, 3]}],
        "outer": {"first": {"x": 1}, "second": {"y": None}, "third": {"z": {"k": 42}}},
    }
    special = {
        "tuple": {"tuple_type": [1, 2, 3]},
        "set": {"set_type": [1, 2, 3]},
        "path": {"path_type": str(Path("some") / "relative" / "path.txt")},
        "datetime": {
            "datetime_type": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC).strftime(
                datetime_format
            )
        },
        "date": {"date_type": date(2024, 1, 2).strftime(date_format)},
        "time": {"time_type": time(3, 4, 5).strftime(time_format)},
        "array": {"numpy_array_type": [[1, 2], [3, 4]]},
    }
    file_path = tmp_path / "config.json"
    file_path.write_text(json.dumps(native | special), encoding="utf-8")

    progress_values = []
    loaded = load_json_progress(file_path, progress_values.append)

    assert progress_values[-1] == 100
    _assert_no_none_keys(loaded)
    for key, value in native.items():
        assert loaded[key] == value
        assert type(loaded[key]) is type(value)
    expected = {
        "tuple": (1, 2, 3),
        "set": {1, 2, 3},
        "path": Path("some") / "relative" / "path.txt",
        "datetime": datetime(2024, 1, 2, 3, 4, 5, tzinfo=UTC),
        "date": date(2024, 1, 2),
        "time": time(3, 4, 5),
    }
    for key, value in expected.items():
        assert loaded[key] == value
        assert isinstance(loaded[key], type(value))
    np.testing.assert_array_equal(loaded["array"], np.array([[1, 2], [3, 4]]))
    assert isinstance(loaded["array"], np.ndarray)
