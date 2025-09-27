"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import functools

from mne_nodes.gui.plot_widgets import show_plot_manager


# ToDo: integrate plot management into exeution pipeline
def pipeline_plot(plot_func):
    @functools.wraps(plot_func)
    def func_wrapper(*args, **kwargs):
        obj = [
            kwargs.get(kw, None)
            for kw in ["meeg", "fsmri", "group"]
            if kwargs.get(kw, None) is not None
        ][0]
        use_plot_manager = obj.ct.settings.value("use_plot_manager")
        if use_plot_manager and "show_plots" in kwargs:
            kwargs["show_plots"] = False
        plot = plot_func(*args, **kwargs)
        if use_plot_manager and plot is not None:
            if not isinstance(plot, list):
                plot = [plot]
            plot_manager = show_plot_manager()
            plot_manager.add_plot(plot, obj.name, plot_func.__name__)

    return func_wrapper
