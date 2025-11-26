"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
Github: https://github.com/marsipu/mne-nodes
"""

import logging
import os
import shutil
from os.path import isdir, isfile
from pathlib import Path

import mne

from mne_nodes.pipeline.loading import MEEG, FSMRI
from mne_nodes.pipeline.pipeline_utils import is_test


def import_raw(name, import_path, controller):
    meeg = MEEG(name, controller)
    raw = mne.io.read_raw(import_path)
    if name not in controller.bad_channels:
        controller.bad_channels[name] = []
    controller.bad_channels[name].append(raw.info["bads"])
    meeg.save_raw(raw)


def import_fsmri(name, import_path, controller):
    dst_dir = controller.subjects_dir / name
    if isdir(dst_dir):
        logging.info(f"Removing existing directory for fsmri data for {name}.")
        shutil.rmtree(dst_dir)
    logging.info(f"Copying fsmri data for {name} to:\n {dst_dir}.")
    shutil.copytree(import_path, dst_dir)
    logging.info(f"FSMRI data for {name} copied to:\n {dst_dir}.")


datasets = {
    "testing": {
        "io_mapping": {
            "raw": "sample_audvis_trunc_raw.fif",
            "erm": "sample_audvis_trunc_raw.fif",
            "events": "sample_audvis_trunc_raw-eve.fif",
            "evoked": "sample_audvis_trunc-ave.fif",
            "noise_cov": "sample_audvis_trunc-cov.fif",
            "trans": "sample_audvis_trunc-trans.fif",
            "forward": "sample_audvis_trunc-meg-eeg-oct-6-fwd.fif",
            "inverse": "sample_audvis_trunc-meg-eeg-oct-6-meg-inv.fif",
            "stcs": "sample_audvis_trunc-meg",
        },
        "load": mne.datasets.testing.data_path,
    },
    "sample": {
        "io_mapping": {
            "raw": "sample_audvis_raw.fif",
            "erm": "ernoise_raw.fif",
            "events": "sample_audvis_raw-eve.fif",
            "evoked": "sample_audvis-ave.fif",
            "noise_cov": "sample_audvis-cov.fif",
            "trans": "all-trans.fif",
            "forward": "sample_audvis-meg-eeg-oct-6-fwd.fif",
            "inverse": "sample_audvis-meg-eeg-oct-6-meg-eeg-inv.fif",
            "stcs": "sample_audvis-meg-eeg",
        },
        "load": mne.datasets.sample.data_path,
    },
}


def import_dataset(controller=None, dataset="testing", group="All"):
    info = datasets.get(dataset)
    if info is None:
        raise ValueError(f"Dataset {dataset} not supported.")
    # Load data
    test_data_folder = info["load"]() / "MEG" / "sample"
    controller.add_data(name=dataset, data_type="raw", group=group)
    # Add dataset to project and update attributes
    erm_path = test_data_folder / info["io_mapping"]["erm"]
    controller.add_data("ermnoise", data_type="raw", input_path=erm_path)
    controller.input_mapping["erm"][dataset] = "ermnoise"
    controller.input_mapping["fsmri"][dataset] = "fsaverage"
    meeg = MEEG(dataset, controller)
    meeg.fsmri = FSMRI("fsaverage", controller)
    # Add event_id
    if dataset not in controller.event_ids:
        meeg.event_id = {
            "auditory/left": 1,
            "auditory/right": 2,
            "visual/left": 3,
            "visual/right": 4,
            "face": 5,
            "buttonpress": 32,
        }
        controller.event_ids[dataset] = meeg.event_id
    else:
        meeg.event_id = controller.event_ids[dataset]

    # ToDo: Here is a problem, since there is no way
    #  to select "auditory/left" from the gui.
    if dataset not in controller.selected_event_ids:
        meeg.sel_trials = {"auditory": None}
        controller.selected_event_ids[dataset] = meeg.sel_trials
    else:
        meeg.sel_trials = controller.selected_event_ids[dataset]
    # init paths again
    meeg.init_paths()

    for data_type, file_name in info["io_mapping"].items():
        test_file_path = test_data_folder / file_name
        file_path = meeg.io_dict[data_type]["path"]
        if data_type == "stcs":
            file_path = file_path["auditory"]
            if not isfile(file_path + "-lh.stc"):
                logging.debug(f"Copying {data_type} from sample-dataset...")
                stcs = mne.source_estimate.read_source_estimate(test_file_path)
                stcs.save(file_path)
        elif isfile(test_file_path) and not isfile(file_path):
            logging.debug(f"Copying {data_type} from sample-dataset...")
            folder = Path(file_path).parent
            if not isdir(folder):
                os.mkdir(folder)
            shutil.copy2(test_file_path, file_path)
            logging.debug("Done!")

    return meeg


def import_fsaverage(controller):
    logging.info("Downloading fsaverage...")
    if is_test():
        orig = mne.datasets.testing.data_path() / "subjects" / "fsaverage"
        dest = controller.subjects_dir / "fsaverage"
        if not isdir(dest):
            shutil.copytree(orig, dest)
    else:
        mne.datasets.fetch_fsaverage()

    fsmri = FSMRI("fsaverage", controller)

    return fsmri
