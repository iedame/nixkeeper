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


def write(projects, index, out_dir=config.OUT_DIR):
    """Write each project's raw Repology data plus index.json. Built from
    scratch in a temporary folder and only then swapped in for out_dir, so
    removed packages disappear and a failed run leaves the previous data intact."""
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
