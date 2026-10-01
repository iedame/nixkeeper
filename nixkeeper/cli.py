"""The `nixkeeper` command: one entry point for the sync and the frequent
checks, with the settings as flags.

    nixkeeper sync | frequent-check | pr-check | paths [--lists PATH]
              [--data-dir DIR] [--notify METHOD]
    nixkeeper --version

Each flag wins over its environment variable (NIXKEEPER_LISTS,
NIXKEEPER_DATA_DIR, NIXKEEPER_NOTIFY), which wins over the default. The old
commands (nixkeeper-sync, nixkeeper-frequent-check, nixkeeper-pr-check) still
work until 1.0, as aliases."""

import argparse
import importlib
import os
import sys
from importlib import metadata

from . import config, notify

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
