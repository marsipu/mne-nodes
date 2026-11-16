# Installation

You need Python 3.11 or newer and a working
[MNE-Python installation](https://mne.tools/stable/install/index.html).
Run the commands below in a terminal with that environment activated.

## Install

```console
python -m pip install mne-nodes
```

| To get | Run |
| --- | --- |
| The latest pre-release | `python -m pip install --upgrade --pre mne-nodes` |
| The development version | `python -m pip install git+https://github.com/marsipu/mne-nodes.git@main` |
| An update of a release | `python -m pip install --upgrade mne-nodes` |

## Start

```console
mne_nodes
```

`python -m mne_nodes` works as well.

On the first start, a welcome tour walks you through a small pipeline. It can
download the MNE sample data, which is large. Restart it any time with
**Help > Restart Welcome Tour**.

Next: [Build and run a pipeline](documentation/pipelines.md).
Processing functions come from [plugins](documentation/plugins.md).
To work on mne-nodes itself, see [Contributing](development/contributing.md).
