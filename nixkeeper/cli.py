"""The `nixkeeper` command: one entry point for the sync and the frequent
checks, with the settings as flags.

    nixkeeper sync | frequent-check | pr-check | paths [--lists PATH]
              [--data-dir DIR] [--notify METHOD]
    nixkeeper init [--maintainer HANDLE ...] [--lists PATH]
    nixkeeper page DIR | serve [--port PORT] [--bind ADDRESS]  [--data-dir DIR]
    nixkeeper --version

Each flag wins over its environment variable (NIXKEEPER_LISTS,
NIXKEEPER_DATA_DIR, NIXKEEPER_NOTIFY), which wins over the default: the
user's own folders (config.py). The old
commands (nixkeeper-sync, nixkeeper-frequent-check, nixkeeper-pr-check) still
work until 1.0, as aliases."""

import argparse
import importlib
import os
import sys
from importlib import metadata

from . import config, init, lock, notify, page

# name: (what it does, the module whose main() runs it)
COMMANDS = {
    "sync": (
        "one full sync: every source, for every tracked package",
        "nixkeeper.sync",
    ),
    "frequent-check": (
        "only the update checks marked frequent, against the last published data",
        "nixkeeper.frequent",
    ),
    "pr-check": (
        "outdated packages' update PRs, open and merged, against the last "
        "published data",
        "nixkeeper.prcheck",
    ),
}

# flag: (the config setting it sets, its environment variable)
SETTINGS = {
    "lists": ("LISTS", "NIXKEEPER_LISTS"),
    "data_dir": ("OUT_DIR", "NIXKEEPER_DATA_DIR"),
    "notify": ("NOTIFY", "NIXKEEPER_NOTIFY"),
}


def version():
    try:
        return metadata.version("nixkeeper")
    except metadata.PackageNotFoundError:  # run from a source tree
        return "unknown"


def parser():
    # The settings, accepted before or after the command. SUPPRESS: a flag
    # left out doesn't overwrite one given in the other position.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--lists",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="the package lists: a Nix folder (package-lists/) or a JSON file "
        "of what it evaluates to (NIXKEEPER_LISTS)",
    )
    common.add_argument(
        "--data-dir",
        metavar="DIR",
        default=argparse.SUPPRESS,
        help="where the data is written, and the last run read from "
        "(NIXKEEPER_DATA_DIR)",
    )
    common.add_argument(
        "--notify",
        choices=["none", *notify.SENDERS],
        default=argparse.SUPPRESS,
        help="how to report what changed (NIXKEEPER_NOTIFY; default: none)",
    )
    p = argparse.ArgumentParser(
        prog="nixkeeper",
        description="Health dashboard for the nixpkgs packages you maintain: "
        "new releases, build and update failures, and vulnerabilities.",
        parents=[common],
    )
    p.add_argument("--version", action="version", version=f"nixkeeper {version()}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")
    for name, (what, _) in COMMANDS.items():
        sub.add_parser(
            name,
            help=what,
            description=f"{what[0].upper()}{what[1:]}.",
            parents=[common],
        )
    sub.add_parser(
        "paths",
        help="where the lists and data are, and which setting says so",
        description="Where the lists and data are, and which setting says so.",
        parents=[common],
    )
    init = sub.add_parser(
        "init",
        help="start your package lists (where --lists says, else the default)",
        description="Start your package lists: a folder of Nix files to edit, "
        "where --lists (or NIXKEEPER_LISTS) says, else the default.",
        parents=[common],
    )
    init.add_argument(
        "--maintainer",
        metavar="HANDLE",
        action="append",
        default=[],
        help="a GitHub handle whose nixpkgs packages to track (repeatable)",
    )
    write = sub.add_parser(
        "page",
        help="write the page and the data into a folder, ready for any static host",
        description="Write the page and a copy of the data into DIR (created "
        "if needed; only an empty folder or an earlier page), ready for any "
        "static host. Run it again after a sync.",
        parents=[common],
    )
    write.add_argument("dir", metavar="DIR", help="the folder to write")
    serve = sub.add_parser(
        "serve",
        help="show the page on this computer, with the data as it is",
        description="Serve the page and the data, as they are (a new sync "
        "shows on the next reload), until Ctrl+C.",
        parents=[common],
    )
    serve.add_argument(
        "--port", type=int, default=8000, help="the port to listen on (default: 8000)"
    )
    serve.add_argument(
        "--bind",
        metavar="ADDRESS",
        default="127.0.0.1",
        help="the address to listen on (default: 127.0.0.1, this computer only)",
    )
    return p


def settings(args):
    """{flag: (value, where it came from)}, flag first, then the environment,
    then the default."""
    found = {}
    for flag, (name, env) in SETTINGS.items():
        if getattr(args, flag, None):
            found[flag] = (getattr(args, flag), f"--{flag.replace('_', '-')}")
        elif os.environ.get(env):
            found[flag] = (os.environ[env], env)
        else:
            found[flag] = (config.DEFAULTS[name], "default")
    return found


def paths(found):
    for flag, label in (("lists", "lists"), ("data_dir", "data"), ("notify", "notify")):
        value, source = found[flag]
        if flag == "notify":
            print(f"{label + ':':7} {value}  ({source})")
            continue
        where = os.path.abspath(value)
        missing = "" if os.path.exists(where) else ", missing"
        print(f"{label + ':':7} {where}  ({source}{missing})")
    try:
        print(f"{'page:':7} {page.page_dir()}  (shipped with nixkeeper)")
    except SystemExit:
        print(f"{'page:':7} not included in this copy of nixkeeper")


def main(argv=None):
    args = parser().parse_args(argv)
    if not args.command:
        parser().print_help(sys.stderr)
        sys.exit(2)
    found = settings(args)
    for flag, (name, _) in SETTINGS.items():
        setattr(config, name, found[flag][0])
    if args.command == "paths":
        paths(found)
        return
    if args.command == "init":
        folder = os.path.abspath(found["lists"][0])
        init.write(folder, args.maintainer)
        print(f"Wrote your package lists to {folder}.")
        if not args.maintainer:
            print("Add your GitHub handle to maintainers in default.nix.")
        print(
            "Next: `nixkeeper sync` writes the data to "
            f"{os.path.abspath(found['data_dir'][0])}."
        )
        return
    if args.command == "page":
        with lock.held():  # not mid-sync: the data is swapped in whole
            folder = page.write(args.dir)
        print(f"Wrote the page and the data to {folder}: host that folder as is.")
        return
    if args.command == "serve":
        page.serve(args.port, args.bind)
        return
    with lock.held():
        importlib.import_module(COMMANDS[args.command][1]).main()


def _alias(command):
    def run():
        print(
            f"nixkeeper-{command} is now `nixkeeper {command}`; the old name "
            "works until 1.0.",
            file=sys.stderr,
        )
        main([command, *sys.argv[1:]])

    return run


# The old commands (pyproject.toml's [project.scripts]).
sync_alias = _alias("sync")
frequent_check_alias = _alias("frequent-check")
pr_check_alias = _alias("pr-check")
