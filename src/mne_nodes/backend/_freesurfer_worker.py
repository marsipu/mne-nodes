"""Standalone child entry point; requires only stdlib plus callable dependencies."""

import importlib
import pickle
import subprocess
import sys
from pathlib import Path


class PathPickler(pickle.Pickler):
    """Reconstruct pathlib values using the receiving OS's concrete Path class."""

    def __init__(self, stream, translate):
        super().__init__(stream, protocol=4)
        self.translate = translate

    def reducer_override(self, obj):
        if isinstance(obj, Path):
            return Path, (self.translate(str(obj)),)
        return NotImplemented


def main() -> None:
    """Load a private request, invoke the callable and persist its result."""
    request, response, mode = sys.argv[1:]
    with open(request, "rb") as stream:
        module, qualname, kwargs = pickle.load(stream)
    function = importlib.import_module(module)
    for part in qualname.split("."):
        function = getattr(function, part)
    result = function(**kwargs)

    def translate(path):
        if mode == "wsl":
            return subprocess.check_output(
                ["wslpath", "-a", "-w", path], text=True
            ).strip()
        return path

    with open(response, "wb") as stream:
        PathPickler(stream, translate).dump(result)


if __name__ == "__main__":
    main()
