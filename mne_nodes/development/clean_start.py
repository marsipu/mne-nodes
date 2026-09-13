from mne_nodes.pipeline.settings import _platform_settings_path

settings_path = _platform_settings_path()

if settings_path.is_file():
    settings_path.unlink()
    print(f"Deleted settings file: {settings_path}")
