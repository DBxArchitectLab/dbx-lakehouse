#!/usr/bin/env bash
# Stores what the workspace group migration needs to sign in to the account as sp-dbx-lakehouse, in the
# sct_dbx_architect_lab scope of dev, uat and prod, and gives sp-dbx-lakehouse READ on the scope:
#
#   sp-dbx-lakehouse-client-id       its application ID
#   sp-dbx-lakehouse-client-secret   its Databricks OAuth secret (the same as in the GitHub environments)
#   databricks-account-id            the Databricks account ID
#
#   bash scripts/put-migration-secrets.sh
#
# Run as a workspace admin of dev, uat and prod. It uses the CLI profiles dev, uat and prod, signing in (browser) only
# where the profile has no valid login yet. Values are asked for once, hidden, and used for all three workspaces. A
# workspace that fails is reported and the others still run; run it again to retry.
set -uo pipefail

client_id="9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
scope="sct_dbx_architect_lab"
workspaces=(
  "dev  https://adb-7405609089943919.19.azuredatabricks.net"
  "uat  https://adb-7405605496889455.15.azuredatabricks.net"
  "prod https://adb-7405604784566671.11.azuredatabricks.net"
)

ask() {  # ask <prompt> <minimum length>: reads a hidden value
  local value
  read -rsp "$1: " value; echo >&2
  if [ "${#value}" -lt "$2" ]; then
    echo "Only ${#value} characters; run the script again and paste the whole value." >&2
    exit 1
  fi
  printf '%s' "$value"
}

# On Windows, winget installs the CLI without always putting it on Git Bash's PATH.
if ! command -v databricks >/dev/null && [ -n "${LOCALAPPDATA:-}" ] && command -v cygpath >/dev/null; then
  for dir in "$(cygpath -u "$LOCALAPPDATA")"/Microsoft/WinGet/Packages/Databricks.DatabricksCLI_*; do
    [ -x "$dir/databricks.exe" ] && PATH="$PATH:$dir"
  done
fi
databricks --version || exit 1
unset DATABRICKS_HOST   # the profiles set the host

account_id="$(ask "Databricks account ID" 36)" || exit 1
client_secret="$(ask "sp-dbx-lakehouse OAuth secret" 20)" || exit 1

store() {  # store <profile> <host>
  local profile="$1" host="$2"
  if ! databricks current-user me -p "$profile" >/dev/null 2>&1; then
    databricks auth login --host "$host" --profile "$profile" || return 1
  fi
  databricks secrets put-secret "$scope" sp-dbx-lakehouse-client-id     --string-value "$client_id"     -p "$profile" &&
  databricks secrets put-secret "$scope" sp-dbx-lakehouse-client-secret --string-value "$client_secret" -p "$profile" &&
  databricks secrets put-secret "$scope" databricks-account-id          --string-value "$account_id"    -p "$profile" &&
  databricks secrets put-acl "$scope" "$client_id" READ -p "$profile" &&
  databricks secrets list-secrets "$scope" -p "$profile"
}

failed=()
for entry in "${workspaces[@]}"; do
  read -r profile host <<<"$entry"
  echo
  echo "== $profile ($host)"
  store "$profile" "$host" || { echo "FAILED in $profile (see the error above)" >&2; failed+=("$profile"); }
done

unset client_secret account_id
echo
if [ "${#failed[@]}" -gt 0 ]; then
  echo "Not stored in: ${failed[*]}. Fix the error shown for it and run the script again." >&2
  exit 1
fi
echo "Done: the three secrets are in dev, uat and prod."
