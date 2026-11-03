"""Create distributable plugin projects without executing their source."""

import ast
import json
import keyword
import re
import shutil
import subprocess
import sysconfig
from dataclasses import dataclass
from importlib import metadata as import_metadata
from pathlib import Path

from packaging.licenses import canonicalize_license_expression
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from mne_nodes.backend.io import TypedJSONEncoder

BSD_LICENSE = """BSD 3-Clause License

Copyright (c) {author}
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution.
3. Neither the name of the copyright holder nor the names of its contributors
   may be used to endorse or promote products derived from this software without
   specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

MIT_LICENSE = """MIT License

Copyright (c) {author}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

LICENSE_TEMPLATES = {"BSD-3-Clause": BSD_LICENSE, "MIT": MIT_LICENSE}


def validate_plugin_name(name: str) -> None:
    """Require a portable Python module name."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) or keyword.iskeyword(name):
        raise ValueError(
            "Plugin names must be Python module names containing only ASCII "
            "letters, digits, and underscores, and cannot be keywords."
        )


@dataclass(frozen=True)
class PluginPackageMetadata:
    """User-supplied distribution metadata for a plugin."""

    distribution_name: str
    description: str
    author: str
    license_expression: str
    version: str = "0.1.0"
    author_email: str = ""
    repository_url: str = ""
    dependencies: tuple[str, ...] = ()
    license_text: str = ""
    initialize_git: bool = False
    initial_branch: str = "main"
    install_package: bool = False
    editable_install: bool = True

    def validate(self) -> None:
        """Validate metadata before creating any files."""
        if not re.fullmatch(
            r"[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?", self.distribution_name
        ):
            raise ValueError("Enter a valid Python distribution name.")
        Version(self.version)
        if not self.description.strip() or not self.author.strip():
            raise ValueError("A description and author are required.")
        if not self.license_expression.strip():
            raise ValueError("Choose a license explicitly before saving.")
        canonicalize_license_expression(self.license_expression)
        if (
            self.license_expression not in LICENSE_TEMPLATES
            and not self.license_text.strip()
        ):
            raise ValueError("Provide the complete text of the selected license.")
        for dependency in self.dependencies:
            requirement = Requirement(dependency)
            if requirement.url:
                raise ValueError(
                    "PyPI dependencies cannot use direct URLs. "
                    "Use a published package name and version constraint."
                )
        if self.initialize_git:
            git = shutil.which("git")
            if git is None:
                raise ValueError("Git is not installed or is not available on PATH.")
            result = subprocess.run(
                [git, "check-ref-format", "--branch", self.initial_branch],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise ValueError(
                    f"Invalid initial Git branch: {self.initial_branch!r}."
                )


def initialize_plugin_repository(destination: Path, branch: str = "main") -> None:
    """Initialize only a new repository; never commit or change an existing one."""
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is not installed or is not available on PATH.")
    if (destination / ".git").exists():
        return
    result = subprocess.run(
        [git, "init", f"--initial-branch={branch}", str(destination.resolve())],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            "The plugin files were saved, but Git initialization failed:\n"
            + (result.stderr.strip() or result.stdout.strip())
        )


def find_plugin_project(path: Path) -> Path | None:
    """Find the nearest project root containing a plugin file."""
    for parent in path.resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return None


def plugin_source_is_installed(path: Path) -> bool:
    """Protect installed distribution files, including arbitrary pip targets."""
    path = path.resolve()
    for key in ("purelib", "platlib"):
        if path.is_relative_to(Path(sysconfig.get_path(key)).resolve()):
            return True
    for distribution in import_metadata.distributions():
        root = Path(str(distribution.locate_file(""))).resolve()
        if not path.is_relative_to(root):
            continue
        # Editable distributions own metadata, not files in their source tree.
        direct_url = distribution.read_text("direct_url.json")
        if direct_url and json.loads(direct_url).get("dir_info", {}).get("editable"):
            continue
        files = distribution.files
        if files is not None and any(
            Path(str(distribution.locate_file(file))).resolve() == path
            for file in files
        ):
            return True
    return False


@dataclass(frozen=True)
class PluginSource:
    """Files belonging to a registered plugin and whether they can be edited."""

    script_path: Path
    config_path: Path
    project_root: Path | None
    installed: bool


def get_plugin_source(
    plugin_meta: dict, device_override: dict | None = None
) -> PluginSource:
    """Resolve source without importing or enabling a registered plugin."""
    paths = dict(plugin_meta)
    if plugin_meta.get("plugin_type") == "path":
        paths.update(device_override or {})
    config_path = paths.get("config_path")
    if not isinstance(config_path, (str, Path)):
        raise TypeError("This plugin has no editable configuration file.")
    config_path = Path(config_path).resolve()
    script_path = Path(
        paths.get("script_path")
        or config_path.with_name(config_path.name.removesuffix("_config.json") + ".py")
    ).resolve()
    if not script_path.is_file() or not config_path.is_file():
        raise FileNotFoundError(
            "The plugin source or configuration is missing. Restore its files "
            "or reinstall it before editing."
        )
    root = find_plugin_project(script_path)
    return PluginSource(
        script_path,
        config_path,
        root,
        plugin_source_is_installed(script_path)
        or plugin_source_is_installed(config_path),
    )


def copy_plugin_source(
    source: PluginSource, destination: Path, metadata: PluginPackageMetadata
) -> PluginSource:
    """Copy an installed plugin and sibling resources into a new local project."""
    import tokenize

    original_dir = source.script_path.parent
    if plugin_source_is_installed(destination):
        raise ValueError("Choose a destination outside the Python environment.")
    if destination.resolve().is_relative_to(original_dir.resolve()):
        raise ValueError("Choose a destination outside the installed plugin directory.")
    plugin_name = source.script_path.stem
    with tokenize.open(source.script_path) as stream:
        code = stream.read()
    config = json.loads(source.config_path.read_text(encoding="utf-8"))
    config_path = create_plugin_package(
        destination, plugin_name, code, config, metadata
    )
    package_dir = config_path.parent
    if (original_dir / "__init__.py").is_file():
        shutil.copytree(
            original_dir,
            package_dir,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
    return PluginSource(
        package_dir / source.script_path.name,
        package_dir / source.config_path.name,
        destination.resolve(),
        False,
    )


def plugin_module_name(plugin_name: str) -> str:
    """Return the namespaced import package for a plugin."""
    validate_plugin_name(plugin_name)
    return f"mne_nodes_{plugin_name}"


def normalize_source_encoding(code: str) -> str:
    """Make an existing encoding cookie agree with the generated UTF-8 file."""
    lines = code.splitlines(keepends=True)
    for index in range(min(2, len(lines))):
        if lines[index].lstrip().startswith("#"):
            lines[index] = re.sub(
                r"coding[:=][ \t]*[-\w.]+", "coding: utf-8", lines[index]
            )
    return "".join(lines)


def create_plugin_package(
    destination: Path,
    plugin_name: str,
    code: str,
    config: dict,
    metadata: PluginPackageMetadata,
) -> Path:
    """Create a src-layout project, refusing to overwrite existing files.

    The destination is the project root, not its parent. Configuration and
    source stay together inside the import package. No source code is executed.
    """
    module_name = plugin_module_name(plugin_name)
    metadata.validate()
    ast.parse(code)
    destination = Path(destination)
    package_dir = destination / "src" / module_name
    script_name = f"{plugin_name}.py"
    config_name = f"{plugin_name}_config.json"
    quote = json.dumps
    dependencies = list(metadata.dependencies)
    if not any(
        canonicalize_name(Requirement(dep).name) == "mne-nodes"
        and Requirement(dep).marker is None
        and not Requirement(dep).extras
        for dep in dependencies
    ):
        dependencies.insert(0, "mne-nodes")
    author = f"name = {quote(metadata.author)}"
    if metadata.author_email:
        author += f", email = {quote(metadata.author_email)}"
    pyproject = f"""[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[project]
name = {quote(metadata.distribution_name)}
version = {quote(metadata.version)}
description = {quote(metadata.description)}
readme = "README.md"
requires-python = ">=3.11"
license = {quote(metadata.license_expression)}
license-files = ["LICENSE"]
authors = [{{ {author} }}]
dependencies = {quote(dependencies)}
classifiers = [
    "Programming Language :: Python :: 3",
    "Intended Audience :: Science/Research",
    "Topic :: Scientific/Engineering",
]

[project.entry-points."mne_nodes.plugins"]
{plugin_name} = {quote(module_name)}
"""
    if metadata.repository_url:
        pyproject += (
            f"\n[project.urls]\nRepository = {quote(metadata.repository_url)}\n"
        )
    pyproject += f"""
[tool.hatch.build.targets.wheel]
packages = ["src/{module_name}"]

[tool.hatch.build.targets.sdist]
include = ["/src", "/pyproject.toml", "/README.md", "/LICENSE"]
"""
    init_code = f'''"""Plugin metadata; implementation imports are deferred until loading."""

from pathlib import Path

PLUGIN_NAME = {quote(plugin_name)}
CONFIG_PATH = Path(__file__).parent / {quote(config_name)}
SCRIPT_PATH = Path(__file__).parent / {quote(script_name)}
'''
    # Keep module identity separate from installation source. A repository URL
    # alone must not make an installed plugin reinstall itself from GitHub.
    readme = f"""# {metadata.distribution_name}

{metadata.description}

## Install and load

Run `python -m pip install .` (or `python -m pip install -e .` for development).
MNE-Nodes discovers and enables newly installed plugins automatically.
Use **Plugins > Manage Plugins** to refresh discovery or enable/disable plugins.
Only explicitly selected plugins are activated in a project.
Without installing, load `src/{module_name}/{config_name}` using
**Plugins > Load Plugin from Path**.

## Build and publish

Review the metadata in `pyproject.toml`, the license, and all runtime dependencies.
Imported helper modules and non-Python resources must also be included in the
package. System tools (for example FreeSurfer) need separate installation and
should be documented here; pip dependencies only describe Python packages.

```shell
python -m pip install build twine
python -m build
python -m twine check dist/*
python -m twine upload dist/*
```

Use a unique distribution name on PyPI and increase the version before each
release. Building works from source archives without Git.

## License

{metadata.license_expression}; see `LICENSE`.
"""
    license_text = metadata.license_text or LICENSE_TEMPLATES[
        metadata.license_expression
    ].format(author=metadata.author)
    files = {
        destination / "pyproject.toml": pyproject,
        destination / "README.md": readme,
        destination / "LICENSE": license_text,
        destination / ".gitignore": (
            "__pycache__/\n*.py[cod]\n.venv/\ndist/\nbuild/\n*.egg-info/\n"
        ),
        package_dir / "__init__.py": init_code,
        package_dir / script_name: normalize_source_encoding(code),
        package_dir / config_name: json.dumps(config, indent=4, cls=TypedJSONEncoder)
        + "\n",
    }
    for path in files:
        if path.exists():
            raise FileExistsError(f"Refusing to overwrite '{path}'.")
    if package_dir.exists():
        raise FileExistsError(f"Package directory already exists: '{package_dir}'.")
    created = []
    try:
        for path, content in files.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(content)
    except OSError:
        for path in reversed(created):
            path.unlink()
        if package_dir.is_dir():
            package_dir.rmdir()
        raise
    return package_dir / config_name
