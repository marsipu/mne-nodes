"""Safe source renaming for locally maintained plugin functions."""

import ast
import io
import json
import keyword
import tokenize
from pathlib import Path

from filelock import FileLock, Timeout

from mne_nodes.backend.io import TypedJSONEncoder
from mne_nodes.backend.plugin_package import (
    normalize_source_encoding,
    plugin_source_is_installed,
)
from mne_nodes.gui.user_interaction import raise_user_attention


def can_rename_plugin_source(plugin_meta: dict) -> bool:
    """Allow source renaming only for existing local or editable plugin files."""
    paths = [plugin_meta.get(key) for key in ("script_path", "config_path")]
    return all(
        isinstance(path, (str, Path))
        and Path(path).is_file()
        and not plugin_source_is_installed(Path(path))
        for path in paths
    )


def rename_plugin_function(plugin_meta: dict, old_name: str, new_name: str) -> bool:
    """Rename a local definition or imported binding and its JSON configuration.

    The old Python name remains an alias, preserving imports and calls from
    other modules. Imported implementations and installed files are untouched.
    """
    return rename_plugin_functions(plugin_meta, {old_name: new_name})


def rename_plugin_functions(plugin_meta: dict, renames: dict[str, str]) -> bool:
    """Rename source/configuration together, notifying the user on failure."""
    try:
        _rename_plugin_functions(plugin_meta, renames)
    except (OSError, ValueError, SyntaxError, tokenize.TokenError, Timeout) as error:
        raise_user_attention(f"Could not rename plugin functions: {error}", "error")
        return False
    return True


def _rename_plugin_functions(plugin_meta: dict, renames: dict[str, str]) -> None:
    for new_name in renames.values():
        if not new_name.isidentifier() or keyword.iskeyword(new_name):
            raise ValueError(f"Invalid function name: {new_name!r}.")
    if len(set(renames.values())) != len(renames):
        raise ValueError("Each renamed function needs a unique name.")
    script_value = plugin_meta.get("script_path")
    config_value = plugin_meta.get("config_path")
    if script_value is None or not isinstance(config_value, (str, Path)):
        raise ValueError("Source renaming requires a local Python/JSON plugin pair.")
    script = Path(script_value)
    config_path = Path(config_value)
    if plugin_source_is_installed(script) or plugin_source_is_installed(config_path):
        raise ValueError(
            "Installed package files cannot be renamed. Use a node alias, or "
            "copy the plugin to a local source project with Manage Plugins > Edit."
        )
    with FileLock(str(config_path) + ".lock"):
        original_script = script.read_bytes()
        original_config = config_path.read_bytes()
        with tokenize.open(script) as stream:
            code = stream.read()
        config = json.loads(original_config)
        for old_name, new_name in renames.items():
            code = _rename_definition(code, old_name, new_name, script)
            if old_name not in config or new_name in config:
                raise ValueError(
                    "The function configuration changed; reload the plugin."
                )
            config[new_name] = config.pop(old_name)
        updated = normalize_source_encoding(code)
        ast.parse(updated)
        # Restore both originals if either write fails; never leave a half rename.
        try:
            script.write_text(updated, encoding="utf-8")
            config_path.write_text(
                json.dumps(config, indent=4, cls=TypedJSONEncoder), encoding="utf-8"
            )
        except OSError:
            script.write_bytes(original_script)
            config_path.write_bytes(original_config)
            raise


def _rename_definition(code: str, old_name: str, new_name: str, script: Path) -> str:
    tree = ast.parse(code)
    bindings = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == old_name:
                bindings.append((node, None))
        elif isinstance(node, ast.ImportFrom):
            bindings.extend(
                (node, alias)
                for alias in node.names
                if (alias.asname or alias.name) == old_name
            )
    if len(bindings) != 1:
        raise ValueError(
            f"{old_name!r} is not a unique top-level definition or import "
            f"in {script}. Use a node alias for class methods."
        )
    tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
    if any(t.type == tokenize.NAME and t.string == new_name for t in tokens):
        raise ValueError(f"{new_name!r} is already used in {script}.")

    # Work in UTF-8 bytes to match AST columns; apply edits backwards so offsets
    # stay valid and the rest of the file keeps its comments and formatting.
    lines = code.encode("utf-8").splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    binding, alias = bindings[0]
    if alias is not None:
        start = offsets[alias.lineno - 1] + alias.col_offset
        end = offsets[(alias.end_lineno or alias.lineno) - 1]
        end += alias.end_col_offset or 0
        replacement = f"{alias.name} as {new_name}"
    else:
        token = next(
            t
            for t in tokens
            if t.type == tokenize.NAME
            and t.string == old_name
            and t.start[0] == binding.lineno
        )
        start = offsets[token.start[0] - 1]
        start += len(token.line[: token.start[1]].encode("utf-8"))
        end = start + len(old_name.encode("utf-8"))
        replacement = new_name
    position = offsets[binding.end_lineno or binding.lineno]
    edits = [
        (start, end, replacement),
        (position, position, f"\n{old_name} = {new_name}\n"),
    ]
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets)
            and isinstance(node.value, (ast.List, ast.Tuple))
            and any(
                isinstance(item, ast.Constant) and item.value == old_name
                for item in node.value.elts
            )
        ):
            position = offsets[node.end_lineno or node.lineno]
            edits.append((position, position, f"\n__all__ += [{new_name!r}]\n"))
            break
    source = code.encode("utf-8")
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement.encode("utf-8") + source[end:]
    return source.decode("utf-8")
