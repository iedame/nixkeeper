# shellcheck shell=bash
# Starts the community instance's runs through GitHub's API (workflow
# dispatch), from a machine that's always on: GitHub's own schedule is
# best-effort and skips runs when it's busy (nixkeeper-hydra's hourly digest
# ran 3 times on 2026-10-06). Run it hourly, a little after the hour (the
# nix-darwin agent in docs/all-packages.md runs it at :15); by the hour in
# UTC it starts:
#
#   every hour      nixkeeper-hydra's digest (stops early with no newer evaluation)
#   every 3 hours   nixkeeper-updates' digest
#   04 UTC          nixkeeper-versions' digest, if its last run is over 12 hours old
#   06 UTC          nixkeeper's daily sync, if the last sync is over 12 hours old
#
# The workflows keep their own schedules as a fallback: a run started twice
# (by both) either waits for the other and finds nothing new, or stops at
# once (if_older).
#
# The token: a fine-grained one for the four repositories with only
# "Actions: read and write" (it can start and cancel runs, nothing else), in
# NIXKEEPER_START_TOKEN_FILE or else the macOS Keychain item
# "nixkeeper-start-runs". --dry-run prints what it would start, without one.
# NIXKEEPER_START_OWNER: whose repositories (default iedame).

set -euo pipefail

owner=${NIXKEEPER_START_OWNER:-iedame}
dry_run=false
case "${1:-}" in
--dry-run) dry_run=true ;;
"") ;;
*)
  echo "usage: start-runs [--dry-run]" >&2
  exit 2
  ;;
esac
hour=$((10#$(date -u +%H)))

token=
if ! $dry_run; then
  if [ -n "${NIXKEEPER_START_TOKEN_FILE:-}" ]; then
    token=$(<"$NIXKEEPER_START_TOKEN_FILE")
  else
    token=$(/usr/bin/security find-generic-password -s nixkeeper-start-runs -w)
  fi
fi

failed=0
start() {
  local repo=$1 workflow=$2 inputs=${3:-"{}"}
  local stamp
  stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if $dry_run; then
    echo "$stamp would start $owner/$repo $workflow $inputs"
    return
  fi
  local code
  code=$(curl --silent --show-error --max-time 30 --output /dev/null \
    --write-out '%{http_code}' --request POST \
    --header "Authorization: Bearer $token" \
    --header "Accept: application/vnd.github+json" \
    --header "X-GitHub-Api-Version: 2022-11-28" \
    --data "{\"ref\":\"main\",\"inputs\":$inputs}" \
    "https://api.github.com/repos/$owner/$repo/actions/workflows/$workflow/dispatches") || code="no answer"
  if [ "$code" = 204 ]; then
    echo "$stamp started $owner/$repo $workflow"
  else
    echo "$stamp FAILED to start $owner/$repo $workflow: $code" >&2
    failed=1
  fi
}

start nixkeeper-hydra digest.yml
if ((hour % 3 == 0)); then
  start nixkeeper-updates digest.yml
fi
if ((hour == 4)); then
  start nixkeeper-versions digest.yml '{"if_older":"12"}'
fi
if ((hour == 6)); then
  start nixkeeper data-daily.yml '{"if_older":"12"}'
fi
exit "$failed"
