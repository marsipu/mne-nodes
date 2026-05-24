"""
Authors: Martin Schulz <dev@mgschulz.de>
License: BSD 3-Clause
GitHub: https://github.com/marsipu/mne-nodes
"""

import sys
import subprocess
import shutil

import os
from os.path import join, isdir

import mne

ismac = sys.platform.startswith("darwin")
iswin = sys.platform.startswith("win32")
islin = not ismac and not iswin


def filter_bandpass(
    raw,
    l_freq: float | None = None,
    h_freq: float | None = None,
    n_jobs: int | str | None = -1,
):
    """Filter raw data."""
    if not raw.preload:
        raw.load_data()
    raw.filter(l_freq=l_freq, h_freq=h_freq, n_jobs=n_jobs)

    return raw


def create_epochs(
    raw,
    events=None,
    event_id: dict | None = None,
    t_epoch: tuple[float, float] = (0, 1),
    baseline: tuple[float, float] | None = None,
):
    # ToDo: Problem what if events as input is not always necessary? Rethink logic of function-recognition?
    if events is None:
        events, event_id = mne.events_from_annotations(raw)

    epochs = mne.Epochs(
        raw=raw,
        events=events,
        event_id=event_id,
        tmin=t_epoch[0],
        tmax=t_epoch[1],
        baseline=baseline,
    )
    return epochs


def create_evokeds(epochs, conditions=None):
    if conditions is not None:
        evokeds = []
        for cond in conditions:
            evoked = epochs[cond].average()
            evokeds.append(evoked)
    else:
        evokeds = epochs.average()

    return evokeds


def plot_evokeds(evokeds):
    evokeds.plot()


def grand_average_evokeds(
    evokeds, interpolate_bads: bool = True, drop_bads: bool = True
):
    evoked_dict = {}
    for evoked in evokeds:
        # Assuming evoked is a list
        for ave in evoked:
            if ave.comment in evoked_dict:
                evoked_dict[ave.comment].append(ave)
            else:
                evoked_dict[ave.comment] = [ave]
    ga_evokeds = []
    for comment, evoked_list in evoked_dict.items():
        ga_evoked = mne.grand_average(
            evoked_list, interpolate_bads=interpolate_bads, drop_bads=drop_bads
        )
        ga_evokeds.append(ga_evoked)

    return ga_evokeds


def plot_ga_evokeds(ga_evokeds):
    mne.viz.plot_compare_evokeds(ga_evokeds)


def run_freesurfer_subprocess(command, subjects_dir, fs_path, mne_path=None):
    # Several experiments with subprocess showed,
    # that it seems impossible to run commands like "source" from
    # a subprocess to get SetUpFreeSurfer.sh into the environment.
    # Current workaround is adding the binaries to PATH manually,
    # after the user set the path to FREESURFER_HOME
    if fs_path is None:
        raise RuntimeError("Path to FREESURFER_HOME not set, can't run this function")
    environment = os.environ.copy()
    environment["FREESURFER_HOME"] = fs_path
    environment["SUBJECTS_DIR"] = subjects_dir
    if iswin:
        command.insert(0, "wsl")
        if mne_path is None:
            raise RuntimeError(
                "Path to MNE-Environment in Windows-Subsytem for Linux(WSL)"
                " not set, can't run this function"
            )

        # Add Freesurfer-Path, MNE-Path and standard Ubuntu-Paths,
        # which get lost when sharing the Path from Windows
        # to WSL
        environment["PATH"] = (
            f"{fs_path}/bin:{mne_path}/bin:"
            f"/usr/local/sbin:"
            f"/usr/local/bin:"
            f"/usr/sbin:"
            f"/usr/bin:"
            f"/sbin:"
            f"/bin"
        )
        environment["WSLENV"] = "PATH/u:SUBJECTS_DIR/p:FREESURFER_HOME/u"
    else:
        # Add Freesurfer to Path
        environment["PATH"] = environment["PATH"] + f":{fs_path}/bin"

    # Add Mac-specific Freesurfer-Paths
    # (got them from FreeSurferEnv.sh in FREESURFER_HOME)
    if ismac:
        if isdir(join(fs_path, "lib/misc/lib")):
            environment["PATH"] = environment["PATH"] + f":{fs_path}/lib/misc/bin"
            environment["MISC_LIB"] = join(fs_path, "lib/misc/lib")
            environment["LD_LIBRARY_PATH"] = join(fs_path, "lib/misc/lib")
            environment["DYLD_LIBRARY_PATH"] = join(fs_path, "lib/misc/lib")

        if isdir(join(fs_path, "lib/gcc/lib")):
            environment["DYLD_LIBRARY_PATH"] = join(fs_path, "lib/gcc/lib")

    # Popen is needed, run(which is supposed to be newer)
    # somehow doesn't seem to support live-stream via PIPE?!
    process = subprocess.Popen(
        command,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )

    # write subprocess-output to main-tread streams
    if process.stdout is not None:
        while process.poll() is None:
            stdout_line = process.stdout.readline()
            if stdout_line is not None:
                sys.stdout.write(stdout_line)


def apply_watershed(fsmri):
    print(
        "Running Watershed algorithm for: "
        + fsmri.name
        + ". Output is written to the bem folder "
        + "of the subject's FreeSurfer folder.\n"
        + "Bash output follows below.\n\n"
    )

    # watershed command
    command = ["mne", "watershed_bem", "--subject", fsmri.name, "--overwrite"]

    run_freesurfer_subprocess(
        command, fsmri.subjects_dir, fsmri.fs_path, fsmri.mne_path
    )

    if iswin:
        # Copy Watershed-Surfaces because the Links don't work
        # under Windows when made in WSL
        surfaces = [
            (f"{fsmri.name}_inner_skull_surface", "inner_skull.surf"),
            (f"{fsmri.name}_outer_skin_surface", "outer_skin.surf"),
            (f"{fsmri.name}_outer_skull_surface", "outer_skull.surf"),
            (f"{fsmri.name}_brain_surface", "brain.surf"),
        ]
        bem_dir = join(fsmri.subjects_dir, fsmri.name, "bem")
        watershed_dir = join(bem_dir, "watershed")
        for src, dst in surfaces:
            # Remove faulty link
            os.remove(join(bem_dir, dst))
            # Copy files
            source = join(watershed_dir, src)
            destination = join(fsmri.subjects_dir, fsmri.name, "bem", dst)
            shutil.copy2(source, destination)

            print(f"{dst} was created")


def make_dense_scalp_surfaces(fsmri):
    print(
        "Making dense scalp surfacing easing co-registration for "
        + "subject: "
        + fsmri.name
        + ". Output is written to the bem folder"
        + " of the subject's FreeSurfer folder.\n"
        + "Bash output follows below.\n\n"
    )

    command = [
        "mne",
        "make_scalp_surfaces",
        "--overwrite",
        f"--subject={fsmri.name}",
        "--force",
    ]

    run_freesurfer_subprocess(
        command, fsmri.subjects_dir, fsmri.fs_path, fsmri.mne_path
    )


# ==============================================================================
# MNE SOURCE RECONSTRUCTIONS
# ==============================================================================


def setup_src(fsmri, src_spacing, surface, n_jobs):
    src = mne.setup_source_space(
        fsmri.name,
        spacing=src_spacing,
        surface=surface,
        subjects_dir=fsmri.subjects_dir,
        add_dist=False,
        n_jobs=n_jobs,
    )
    fsmri.save_source_space(src)


def setup_vol_src(fsmri, vol_src_spacing):
    bem = fsmri.load_bem_solution()
    vol_src = mne.setup_volume_source_space(
        fsmri.name, pos=vol_src_spacing, bem=bem, subjects_dir=fsmri.subjects_dir
    )
    fsmri.save_volume_source_space(vol_src)


def compute_src_distances(fsmri, n_jobs):
    src = fsmri.load_source_space()
    src_computed = mne.add_source_space_distances(src, n_jobs=n_jobs)
    fsmri.save_source_space(src_computed)


def prepare_bem(fsmri, bem_spacing, bem_conductivity):
    bem_model = mne.make_bem_model(
        fsmri.name,
        subjects_dir=fsmri.subjects_dir,
        ico=bem_spacing,
        conductivity=bem_conductivity,
    )
    fsmri.save_bem_model(bem_model)

    bem_solution = mne.make_bem_solution(bem_model)
    fsmri.save_bem_solution(bem_solution)


def create_forward_solution(meeg, n_jobs, ch_types):
    info = meeg.load_info()
    trans = meeg.load_transformation()
    bem = meeg.fsmri.load_bem_solution()
    src = meeg.fsmri.load_source_space()

    if "eeg" in ch_types:
        eeg = True
    else:
        eeg = False

    forward = mne.make_forward_solution(info, trans, src, bem, eeg=eeg, n_jobs=n_jobs)

    meeg.save_forward(forward)
