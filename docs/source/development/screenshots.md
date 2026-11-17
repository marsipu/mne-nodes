# Documentation screenshots

Every image in this documentation is generated from the running application.
`development/screenshots.py` reads scenarios from
`docs/screenshots/screenshots.toml`, performs their steps in a disposable
project, and saves one PNG per scenario.

## Generate and preview

```console
python -m development.screenshots                 # all screenshots
python -m development.screenshots add-node groups # only some
python -m development.screenshots --list          # show the names
zensical serve                                    # preview the site
```

* Images go to `docs/source/_static/screenshots/linux`, the folder the pages
  link to on every platform. It is ignored by Git.
* Set `QT_SCALE_FACTOR=1` on HiDPI screens. Windows open briefly while
  capturing. A headless Linux machine needs `xvfb-run -a`.
* The `Render Documentation` workflow captures on `ubuntu-latest`, checks that
  every configured screenshot exists, and builds with `zensical build --strict`.
  Pull requests upload the site as the `html-docs` artifact; pushes to `main`
  deploy it to GitHub Pages (**Settings > Pages > Source: GitHub Actions**).

## Add a screenshot

1. Add a `[[screenshots]]` entry to `docs/screenshots/screenshots.toml`.
2. Generate it and look at the result.
3. Reference it in a page:
   `![Description](../_static/screenshots/linux/<name>.png)`.

This entry produces the image below it:

```toml
[[screenshots]]
name = "connect-ports"            # output file: connect-ports.png
capture = "viewer"                # widget to capture, default "window"
window_size = [1000, 560]         # size of the main window
steps = [
    { call = "output:prepare_eeg.raw.disconnect_from", args = ["@input:example_filter.raw"] },
    { call = "viewer.zoom_to_nodes", args = [["@node:prepare_eeg", "@node:example_filter"]] },
    { drag = "output:prepare_eeg.raw", to = "input:example_filter.raw", offset = [-40, 0], release = false },
]

[[screenshots.highlights]]
target = "output:prepare_eeg.raw"
text = "Drag from an output port"
position = "top"

[[screenshots.highlights]]
target = "input:example_filter.raw"
text = "Release on a compatible input"
color = "#1e88e5"
position = "top"
```

![The generated connect-ports screenshot](../_static/screenshots/linux/connect-ports.png)

Use `size = [width, height]` instead of `window_size` to fix the size of a
captured dialog. Unknown keys and targets that cannot be resolved fail the run.

## The project

Each screenshot starts from a fresh copy of the `[project]` table: the tiny
BIDS test dataset, the packaged example plugin, and the illustrative functions
in `docs/screenshots/documentation_processing.py`. Settings, data, and
generated files live in a temporary folder, and nothing is downloaded.

```toml
[project]
dataset = "../../tests/tiny_bids"           # copied for every screenshot
plugins = ["resource:example_plugin_config.json"]
inputs = { eeg = ["*.vhdr"] }               # checked recordings per datatype
connections = ["input.eeg -> prepare_eeg.raw"]

[[project.imports]]                         # Python file saved as a plugin
file = "documentation_processing.py"
plugin_name = "documentation_processing"

[[project.nodes]]
function = "example_filter"
parameters = { highpass = 5 }
```

Paths are relative to the TOML file; `resource:` points into
`mne_nodes.resources`. Nodes are laid out automatically unless
`auto_layout = false` and each node has a `position`.

## Steps

Each step has one action whose value is its target.

| Action | Options | Effect |
| --- | --- | --- |
| `click` | `item`, `button`, `double` | Click a widget, a view item, or a graph item |
| `hover` | `item` | Move the mouse over a target |
| `drag` | `to` or `by`, `offset`, `release`, `moves`, `button` | Drag; `release = false` captures mid-drag |
| `menu` | `item`, `offset` | Open a menu-bar menu, or the context menu of a widget or graph item |
| `select` | `item` | Select a view item, combo-box entry, tab, or node |
| `type` | `text` | Type into a widget |
| `key` | `target` | Press a key sequence such as `"Ctrl+S"` |
| `set` | `value` | Set an attribute, Qt property, or dictionary entry |
| `call` | `args`, `kwargs`, `store` | Call a method and optionally store the result |
| `create` | `args`, `kwargs`, `store` | Call a class or function by import path, such as a dialog |
| `resize` | `size`, `width`, `height` | Fix the size of a widget |
| `run` | `timeout` | Run the listed nodes and wait for success |
| `wait` | `timeout` | Wait for milliseconds, or until a target path is true |
| `recipe` | `kwargs` | Call a Python helper registered with `@recipe` |

Menus stay open for the capture. `item` highlights an entry; separate nested
entries with ` > `:

```toml
steps = [{ menu = "viewer", item = "documentation_processing > create_epochs" }]
```

![The generated add-node screenshot with an open context menu](../_static/screenshots/linux/add-node.png)

## Targets

A target is a dot-separated path.

| Start | Refers to |
| --- | --- |
| `window`, `viewer`, `controller`, `app` | The main objects of the application |
| A stored name | The result of a `call` or `create` step with `store` |
| `node:example_filter` | A node; `node:input` is the input node |
| `output:prepare_eeg.raw`, `input:example_filter.raw` | A port |

Every further segment is looked up as an attribute, dictionary key, list index,
Qt object name, or the text of a child widget such as a button or a menu
(`window.File`, `importer.Load File`). A trailing `()` calls a method.

In `args`, `kwargs`, and `value`, a string starting with `@` is resolved as a
target, and `resource:` or `path:` strings become paths. Write `@@` for a
literal `@`.

## Highlights

Highlights are drawn onto the finished image.

| Key | Meaning |
| --- | --- |
| `target`, `item` | The widget, layout, view item, or graph item to frame |
| `rect` | Alternatively `[x, y, width, height]` in image pixels |
| `text` | Label next to the frame |
| `position` | `bottom`, `top`, `left`, `right`, or `inside`; flips when it does not fit |
| `color`, `text_color`, `fill`, `width`, `padding` | Appearance |

## Limits

* Prefer real interactions and public methods. Use a `@recipe` only for states
  that steps cannot build, such as the synthetic data of the coregistration
  dialog.
* Context menus are captured only when mne-nodes creates them.
* Qt drag-and-drop between widgets (`QDrag`) cannot be simulated; dragging
  inside the node graph works.
* The demo analysis and the coregistration example use synthetic data. They
  illustrate the interface, not a valid analysis.
