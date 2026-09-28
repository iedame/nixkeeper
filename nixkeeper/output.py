"""Writing data/ for the page."""

import json
import os
import re
import shutil

from . import config


def data_file(key):
    """File name for a project's raw data: Repology names like python:requests
    contain characters that don't belong in file names or URLs."""
    return re.sub(r"[^A-Za-z0-9._+-]", "_", key) + ".json"


def write(projects, index, out_dir=None):
    """Write each project's raw Repology data plus index.json. Built from
    scratch in a temporary folder and only then swapped in for out_dir, so
    removed packages disappear and a failed run leaves the previous data intact."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    tmp_dir = out_dir + ".tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)  # leftover from a failed run
    os.makedirs(tmp_dir)
    for proj in projects.values():
        with open(os.path.join(tmp_dir, proj["dataFile"]), "w") as f:
            json.dump(proj["entries"], f, indent=2, sort_keys=True)
    with open(os.path.join(tmp_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=2, sort_keys=True)
    shutil.rmtree(out_dir, ignore_errors=True)
    os.rename(tmp_dir, out_dir)


def update(files, out_dir=None):
    """Replace some files in an existing out_dir ({file name: data}), each
    written aside first so a failure never leaves one half-written. For
    partial runs (the quick check), which leave everything else as it was."""
    out_dir = out_dir or config.OUT_DIR  # the setting now, not at import
    for name, data in files.items():
        path = os.path.join(out_dir, name)
        with open(path + ".tmp", "w") as f:
            json.dump(data, f, indent=2, sort_keys=True)
        os.replace(path + ".tmp", path)
