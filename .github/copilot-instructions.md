# MNE-Nodes Development Instructions

MNE-Nodes is a PyQt6/PySide6 GUI application for MEG/EEG neurophysiology data processing built on top of MNE-Python. This is a complex scientific application with node-based pipeline workflows for processing brain signals.

**Always reference these instructions first and fallback to search or bash commands only when you encounter unexpected information that does not match the info here.**

## Working Effectively

### Installation and Setup
**NEVER CANCEL: Installation can take 15-20 minutes due to large scientific packages (VTK, MNE, Qt). Set timeout to 30+ minutes.**

Install development environment:
```bash
# Install Qt backend first (choose one)
pip install PySide6  # Recommended
# OR: pip install PyQt6

# Install package in development mode with all dependencies
pip install -e .[test]  # For testing dependencies
# OR: pip install -e .[dev]  # For development dependencies
# OR: pip install -e .[docs]  # For documentation dependencies

# Install pre-commit hooks for code quality
pre-commit install
```

**Installation Notes:**
- Large packages like VTK (~100MB+) may cause network timeouts
- If installation fails with timeout, retry with: `pip install --timeout=600 -e .[test]`
- Qt backend (PySide6 or PyQt6) must be installed explicitly before main package
- Development dependencies include: pytest, pytest-qt, ruff, pre-commit

### Headless Display Setup (Required for GUI Testing)
**CRITICAL: Required for any GUI testing or CI environments**

```bash
# For Ubuntu/Debian systems
sudo apt update
sudo apt-get install -y xvfb x11-xserver-utils herbstluftwm
sudo apt-get install -y libgl1 libegl1 libopengl0 libxcb-cursor0 libxcb-icccm4 
sudo apt-get install -y libxcb-image0 libxcb-keysyms1 libxcb-randr0 libxcb-render-util0
sudo apt-get install -y libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0 libxcb-xinput0
sudo apt-get install -y libxkbcommon-x11-0 mesa-utils

# Start virtual display
export DISPLAY=:99.0
Xvfb :99 -screen 0 1024x768x24 > /dev/null 2>&1 &
sleep 3
herbstluftwm &
sleep 3
```

### Building and Testing
**NEVER CANCEL: Test suite may take 10-15 minutes including data downloads. Set timeout to 30+ minutes.**

```bash
# Run all tests
pytest

# Run specific test file
pytest mne_nodes/tests/test_app.py

# Run tests with verbose output
pytest -v

# Run tests for specific components
pytest mne_nodes/tests/test_controller.py
pytest mne_nodes/tests/test_main_window.py
pytest mne_nodes/tests/test_nodes.py
```

**Testing Notes:**
- First test run downloads MNE sample datasets (~500MB+) which takes 5-10 minutes
- Subsequent runs use cached data and are much faster
- pytest-qt handles GUI component testing
- Tests require headless display setup in CI/headless environments

### Running the Application

```bash
# GUI mode (default)
mne_nodes
# OR: python -m mne_nodes

# Debug mode (set environment variable)
MNENODES_DEBUG=true mne_nodes
```

**Application Notes:**
- GUI mode requires Qt backend and display
- Debug mode enables detailed logging
- Application supports both PyQt6 and PySide6 backends

### Code Quality and Linting
**Always run before committing to avoid CI failures**

```bash
# Format code with ruff
ruff format .

# Check code style and fix automatically
ruff check --fix .

# Run pre-commit hooks manually
pre-commit run --all-files

# Check specific file
ruff check mne_nodes/specific_file.py
```

**Linting Notes:**
- ruff handles both formatting and linting
- Pre-commit hooks run ruff, pyupgrade, docformatter automatically
- CI will fail if code doesn't pass ruff checks
- Some syntax warnings in syntax_highlight.py are known (escape sequences)

### Documentation
**NEVER CANCEL: Documentation build takes 5-10 minutes. Set timeout to 20+ minutes.**

```bash
cd docs
make html

# View documentation locally
make view
# OR: python -c "import webbrowser; webbrowser.open_new_tab('file://$(pwd)/build/html/index.html')"

# Clean build
make clean
make html
```

**Documentation Notes:**
- Uses Sphinx with autodoc for API documentation
- Requires package to be installed (imports mne_nodes.gui.parameter_widgets)
- Built docs are deployed to GitHub Pages on main branch
- Documentation source is in docs/source/

## Validation Scenarios

**Always test these scenarios after making changes:**

### Basic Functionality Validation
```bash
# Test basic package imports (without Qt dependencies)
python -c "
import sys; sys.path.insert(0, '.')
import mne_nodes
print(f'Package loaded, GUI mode: {mne_nodes.gui_mode}')
print(f'Platform: Linux={mne_nodes.islin}, Mac={mne_nodes.ismac}, Win={mne_nodes.iswin}')
"

# Note: Full functionality requires Qt backend installation
# After installing PySide6/PyQt6, test with: python -c "import mne_nodes.__main__"
```

### GUI Application Testing (requires headless display)
```bash
# Test application help
python -m mne_nodes --help
```

### Development Workflow Testing
```bash
# Test git status
git status

# Test pre-commit hooks
pre-commit run --all-files

# Test specific linting
ruff check mne_nodes/
ruff format --check mne_nodes/
```

## Key Projects and Locations

### Core Application Structure
- `mne_nodes/__main__.py` - Application entry point, handles GUI/headless mode
- `mne_nodes/__init__.py` - Package initialization, platform detection
- `mne_nodes/gui/` - PyQt GUI components and widgets
- `mne_nodes/pipeline/` - Data processing pipeline and function execution
- `mne_nodes/tests/` - Test suite with pytest and pytest-qt

### Important Configuration Files
- `pyproject.toml` - Modern Python packaging, dependencies, tool configuration
- `.pre-commit-config.yaml` - Code quality hooks (ruff, pyupgrade, docformatter)
- `.github/workflows/run_tests.yml` - CI testing pipeline
- `.github/workflows/docs.yml` - Documentation building pipeline
- `mne_nodes/pytest.ini` - pytest configuration with debug logging

### Development and Documentation
- `mne_nodes/development/` - Development tools and considerations
- `docs/source/` - Sphinx documentation source
- `docs/Makefile` - Documentation build system

## Common Commands and Expected Timing

| Command | Expected Time | Timeout Setting |
|---------|---------------|-----------------|
| `pip install -e .[test]` | 15-20 minutes | 30+ minutes |
| `pytest` (first run) | 10-15 minutes | 30+ minutes |
| `pytest` (subsequent) | 2-5 minutes | 10+ minutes |
| `pre-commit run --all-files` | 1-2 minutes | 5+ minutes |
| `ruff check .` | 10-30 seconds | 2+ minutes |
| `make html` (docs) | 5-10 minutes | 20+ minutes |

## Troubleshooting

### Network/Installation Issues
- **pip timeouts**: Use `pip install --timeout=600` for large packages
- **pip connection errors**: PyPI connectivity issues are common due to large scientific packages
- **VTK installation fails**: May require system graphics libraries or conda instead of pip
- **Qt backend not found**: Ensure PySide6 or PyQt6 installed first before main package
- **Dependency resolution timeout**: Try installing packages individually: `pip install numpy scipy matplotlib` then `pip install -e .`

### GUI/Display Issues  
- **GUI tests fail**: Verify headless display setup (Xvfb, herbstluftwm)
- **Application won't start**: Check Qt backend installation
- **Import errors**: Ensure package installed in development mode

### Testing Issues
- **Dataset download fails**: Check network connectivity, may need retry
- **Tests timeout**: First run downloads large datasets, subsequent runs faster
- **pytest-qt errors**: Verify headless display configuration

## Specific Notes for Different Platforms

### Linux (Ubuntu/Debian)
- Requires headless display packages for GUI testing
- System packages: `xvfb`, `herbstluftwm`, various `libxcb-*` packages
- Works with both PySide6 and PyQt6

### macOS
- Native Qt support, no headless display setup needed for local development
- Menu bar considerations for native macOS behavior
- Modal dialogs may need custom close buttons

### Windows
- Qt applications work natively
- Consider path separators in file operations
- Testing may require different display setup

Remember: **NEVER CANCEL long-running operations**. Scientific package installation and data downloads require patience. Always set appropriate timeouts and wait for completion.