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
# Run as a workspace admin of dev, uat and prod; it signs in to each workspace in the browser. Values are asked for
# once, hidden, and used for all three workspaces.
set -euo pipefail

client_id="9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
scope="sct_dbx_architect_lab"
hosts=(
  https://adb-7405609089943919.19.azuredatabricks.net   # dev
  https://adb-7405605496889455.15.azuredatabricks.net   # uat
  https://adb-7405604784566671.11.azuredatabricks.net   # prod
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
databricks --version
account_id="$(ask "Databricks account ID" 36)"
client_secret="$(ask "sp-dbx-lakehouse OAuth secret" 20)"

for host in "${hosts[@]}"; do
  echo
  echo "== $host"
  export DATABRICKS_HOST="$host"
  databricks auth login --host "$host"
  databricks secrets put-secret "$scope" sp-dbx-lakehouse-client-id     --string-value "$client_id"
  databricks secrets put-secret "$scope" sp-dbx-lakehouse-client-secret --string-value "$client_secret"
  databricks secrets put-secret "$scope" databricks-account-id          --string-value "$account_id"
  databricks secrets put-acl "$scope" "$client_id" READ
  databricks secrets list-secrets "$scope"
done

unset DATABRICKS_HOST
echo
echo "Done: the three secrets are in dev, uat and prod."
