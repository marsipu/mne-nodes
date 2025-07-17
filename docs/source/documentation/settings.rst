Settings
========
There are two different ways, application settings are stored in MNE-Nodes.
It depends on whether the settings is device-specific or user-specific.
For device-specific settings, such as the number of jobs or if cuda is enabled are stored either with *QSettings*, when PyQt/PySide is available, or in a JSON file located in the user's home directory.
The user-specific settings are used to store user preferences, such as the last used directory, the default file format for saving figures, and other application-specific configurations.
