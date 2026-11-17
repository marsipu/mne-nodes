# Create your own nodes

The function importer turns Python functions into nodes. You write the
function; the importer creates the node definition and packages both as a
plugin.

## 1. Write a function

```python
def example_filter(raw, highpass=1, lowpass=30):
    """Filter a recording."""
    raw = raw.filter(highpass, lowpass)
    return raw
```

| In the function | Becomes |
| --- | --- |
| Arguments without a default (`raw`) | Input ports |
| Arguments with a default (`highpass=1`) | Parameters |
| Returned variables (`return raw`) | Output ports |
| The docstring | The description of the node |

Return plain variable names, such as `return raw` or `return epochs, evoked`.
Keep imports and helper functions in the same file.

## 2. Import it

Choose **Plugins > Import Functions...** and click **Load File**. You can also
drop a `.py` file onto the main window or paste code with `Ctrl+V`.

![The function importer with code on the left and the node definition on the right](../_static/screenshots/linux/function-importer.png)

| Control | Purpose |
| --- | --- |
| Arrows button | Switch an argument between input and parameter |
| Gear button | Configure an input, output, or parameter |
| **target** | `file` runs once per recording, `group` once per group |
| **Run in FreeSurfer environment** | Only for functions that need [FreeSurfer](freesurfer.md) |
| **Change Function Description** | Edit the text shown to users |
| **Re-analyze Code** | Update the definition after editing the code |

The gear button of a parameter selects its widget and default value.

![The parameter configuration dialog](../_static/screenshots/linux/configure-parameter.png)

The gear button of an input or output sets the accepted connections. To
[save results](derivatives.md), also enter the load or save function and the
BIDS suffix there.

## 3. Save as a plugin

Click **Save**, fill in the package details, and choose a folder.

![The plugin package dialog](../_static/screenshots/linux/plugin-package.png)

This creates an installable Python project and loads it as a plugin. The new
nodes are in the right-click menu of the canvas.

* Existing files are never overwritten, and your original file stays untouched.
* Initializing Git and installing the package are optional. Nothing is
  committed or uploaded.

To change the plugin later, use **Plugins > Manage Plugins > Edit...**. Saving
there overwrites the local plugin files.

!!! warning
    Loading a file into the importer only analyzes it. Saving loads the plugin,
    which runs its code. Only import code you trust.

Next: [share the plugin](sharing.md).
