#!/usr/bin/env python
"""Test script for the HierarchicalDictWidget implementation.

This script creates a sample hierarchical dictionary and displays it
using the widget.
"""

import sys
from qtpy.QtWidgets import QApplication, QMainWindow
from mne_nodes.gui.base_widgets import TreeWidget


def main():
    # Create a sample hierarchical dictionary with multiple levels of nesting
    sample_data = {
        "level1_item1": {
            "level2_item1": {
                "level3_item1": "value1",
                "level3_item2": "value2",
                "level3_item3": {
                    "level4_item1": "deep_value1",
                    "level4_item2": "deep_value2",
                },
            },
            "level2_item2": "value3",
        },
        "level1_item2": "value4",
        "level1_item3": {
            "level2_item3": "value5",
            "level2_item4": {
                "level3_item4": "value6",
                "level3_item5": [1, 2, 3, 4],  # Test with a list value
                "level3_item6": {
                    "level4_item3": "deep_value3",
                    "level4_item4": {
                        "level5_item1": "very_deep_value",
                        "level5_item2": 12345,  # Test with a numeric value
                    },
                },
            },
        },
        "level1_item4": {
            "empty_dict": {}  # Test with an empty dictionary
        },
    }

    # Create the application
    app = QApplication(sys.argv)

    # Create a main window to hold our widget
    main_window = QMainWindow()
    main_window.setWindowTitle("HierarchicalDictWidget Test")
    main_window.setGeometry(100, 100, 800, 600)

    # Create the hierarchical dict widget with our sample data
    widget = TreeWidget(
        data=sample_data, headers=["Key", "Value"], title="Hierarchical Dictionary Test"
    )

    # Set the widget as the central widget of the main window
    main_window.setCentralWidget(widget)

    # Show the main window
    main_window.show()

    # Start the application event loop
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
