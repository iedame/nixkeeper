"""nixkeeper-hydra's digest of Hydra's builds
(https://github.com/iedame/nixkeeper-hydra): every job of Hydra's newest
evaluation of nixpkgs master, with its newest finished build and, when that
isn't a success, the last successful one, in one download. The daily sync
takes the jobs it can answer from it instead of asking Hydra about each
(hydra.py); Hydra is still asked about the rest, and about everything when
the digest isn't current or can't be read."""

import csv
import gzip
import io
import json
import re
import sys
import urllib.error
from datetime import datetime, timedelta

from .. import config
from . import http

FORMAT = 1
EVAL = re.compile(r"/eval/([0-9]+)")
# The digest's statuses nixkeeper takes as they are; "queued" (a job new to
# the digest, not built yet) is asked of Hydra.
FINISHED = {"ok", "failed", "dependency", "unfinished"}
LAST_SUCCESS = ("lastSuccess", "lastSuccessBuild", "lastSuccessName")


def newest_eval():
    """The id of Hydra's newest evaluation of the jobset, from its list of
    evaluations (one small page). Not its latest-eval: that's the newest
    whose builds have all finished, often a day behind."""
    path = f"/jobset/{config.HYDRA_PROJECT}/{config.HYDRA_JOBSET}/evals"
    page = http.get(config.HYDRA_URL + path) or ""
    ids = [int(i) for i in EVAL.findall(page)]
    if not ids:
        raise ValueError("Hydra's list of evaluations has none")
    return max(ids)


def current(meta, now):
    """Why the digest can be used (its meta.json), or None: it's Hydra's
    newest evaluation, or behind it but read within
    HYDRA_DIGEST_MAX_AGE_HOURS (its workflow catches up hourly)."""
    read = datetime.fromisoformat(meta["fetchedAt"])
    hours = (datetime.fromisoformat(now) - read) / timedelta(hours=1)
    try:
        newest = newest_eval()
    except (urllib.error.URLError, OSError, ValueError) as e:
        newest, why_not = None, f"Hydra's newest evaluation unknown: {e}"
    else:
        if meta["eval"] == newest:
            return f"evaluation {newest}, Hydra's newest"
        why_not = f"evaluation {meta['eval']}; Hydra's newest is {newest}"
    if hours <= config.HYDRA_DIGEST_MAX_AGE_HOURS:
        return f"{why_not}, but read {hours:.0f} h ago"
    return None


def load(now):
    """The digest's rows by (attr, system), or None (saying why) when it's
    turned off, not current (current) or can't be read."""
    base = config.HYDRA_DIGEST_URL
    if not base:
        return None
    try:
        meta = json.loads(http.get(base + "meta.json") or "null")
        if not meta or meta.get("format") != FORMAT:
            raise ValueError(f"no digest in a format this nixkeeper reads ({base})")
        why = current(meta, now)
        if not why:
            print(
                f"::warning::Hydra digest: not used, it's from {meta['fetchedAt']} "
                f"(evaluation {meta['eval']}); asking Hydra about each job",
                file=sys.stderr,
            )
            return None
        body = http.get_bytes(base + "builds.csv.gz")
        if body is None:
            raise ValueError("its builds.csv.gz is missing")
        text = gzip.decompress(body).decode()
        rows = {(r["attr"], r["system"]): r for r in csv.DictReader(io.StringIO(text))}
    except (urllib.error.URLError, OSError, ValueError, KeyError, csv.Error) as e:
        print(
            f"::warning::Hydra digest: couldn't use it ({e}); asking Hydra about "
            "each job",
            file=sys.stderr,
        )
        return None
    print(f"Hydra digest: {len(rows):,} jobs, {why}", file=sys.stderr)
    return rows


def answer(row, broken, before):
    """A job's result from its digest row, as hydra.check gives it, or None
    when the digest can't say: the job is queued there, or its build isn't
    a success and nothing says when it last was. broken: nixpkgs marks it
    broken on that platform. before: the job's result at the last sync, whose
    last success still holds for the same build."""
    if row["status"] not in FINISHED:
        return None
    result = {
        "attr": row["attr"],
        "system": row["system"],
        "status": row["status"],
        "build": int(row["build"]),
    }
    if row["name"]:
        result["name"] = row["name"]
    if broken or row["status"] != "ok":
        if row["status"] == "ok":  # broken, but built: that's its last success
            last = {
                "lastSuccess": row["finished"],
                "lastSuccessBuild": result["build"],
                "lastSuccessName": row["name"],
            }
        elif row["lastSuccessBuild"]:
            last = {
                "lastSuccess": row["lastSuccessAt"],
                "lastSuccessBuild": int(row["lastSuccessBuild"]),
                "lastSuccessName": row["lastSuccessName"],
            }
        elif (
            before
            and before.get("build") == result["build"]
            and "lastSuccess" in before
        ):
            last = {k: before[k] for k in LAST_SUCCESS if k in before}
        else:
            return None
        result.update({k: v for k, v in last.items() if v not in ("", None)})
        result.setdefault("lastSuccess", None)  # never, as Hydra would say
    if broken:
        result["status"] = "broken"
    return result


def answers(digest, wanted, broken, before):
    """({job: result} for the jobs in wanted ([(attr, system)]) the digest
    answers, [the jobs it has that Hydra must still be asked about: queued,
    or a failing build without a known last success]). Jobs missing from it
    are in neither: they're asked as before (hydra.due). broken: {attr:
    [systems]}; before: the last sync's results by job (hydra.last_run)."""
    found, ask = {}, []
    for attr, system in wanted:
        row = digest.get((attr, system))
        if row is None:
            continue
        result = answer(row, system in broken.get(attr, []), before.get((attr, system)))
        if result is None:
            ask.append((attr, system))
        else:
            found[attr, system] = result
    return found, ask


def bulk_answers(digest, wanted, broken, before):
    """{job: result} for every job in wanted, without asking Hydra (with every
    package tracked, the jobs of packages not on the lists): the digest's
    answer (answers); a finished build whose last success it can't say,
    without one; a job it doesn't have, not built (the digest has every job
    of the evaluation: Hydra would say the same), or broken; a queued job,
    as the last sync had it (unknown if it had none). digest None (not
    current): every job as the last sync had it."""
    found = {}
    for attr, system in wanted:
        job = (attr, system)
        is_broken = system in broken.get(attr, [])
        old = before.get(job)
        row = digest.get(job) if digest is not None else None
        if digest is not None and row is None:
            found[job] = {
                "attr": attr,
                "system": system,
                "status": "broken" if is_broken else "notBuilt",
            }
            continue
        result = row and answer(row, is_broken, old)
        if result is None and row and row["status"] in FINISHED:
            result = {
                "attr": attr,
                "system": system,
                "status": "broken" if is_broken else row["status"],
                "build": int(row["build"]),
            }
            if row["name"]:
                result["name"] = row["name"]
        if result is None:
            result = (
                {k: v for k, v in old.items() if k != "checkedAt"}
                if old
                else {"attr": attr, "system": system, "status": "unknown"}
            )
        found[job] = result
    return found
