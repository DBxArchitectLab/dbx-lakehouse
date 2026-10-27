#!/usr/bin/env bash
# Copies everything under src/notebooks/shared to /Workspace/Shared in the workspace of a bundle target, keeping
# subfolders. Notebooks (.py files starting with "# Databricks notebook source") arrive as notebooks.
#
#   scripts/deploy-shared-notebooks.sh <target>      # dev-shared, uat or prod
#
# Uses the same sign-in as the bundle commands (DATABRICKS_CLIENT_ID / _SECRET in the pipeline). Existing objects
# with the same name are overwritten; objects removed from the folder are not deleted from the workspace.
set -euo pipefail

target="${1:?usage: $0 <bundle target>}"
source_dir="src/notebooks/shared"
dest_dir="/Workspace/Shared"

# The workspace host comes from the bundle target, so it is defined in databricks.yml only.
DATABRICKS_HOST="$(databricks bundle validate -t "$target" -o json | jq -r .workspace.host)"
export DATABRICKS_HOST
source_path="$(pwd)/$source_dir"

# Run the workspace commands outside the bundle folder: inside it, the CLI signs in to the bundle's default target
# (dev) and ignores DATABRICKS_HOST, so every environment's copy would land in dev.
cd "${RUNNER_TEMP:-${TMPDIR:-/tmp}}"

echo "Copying $source_dir to $dest_dir on $DATABRICKS_HOST"
databricks workspace import-dir "$source_path" "$dest_dir" --overwrite

# Prove each object is in this workspace (fails the step otherwise).
find "$source_path" -type f | while read -r file; do
  relative="${file#"$source_path"/}"
  case "$file" in
    *.py | *.sql | *.scala | *.r | *.R) head -1 "$file" | grep -q "Databricks notebook source" && relative="${relative%.*}" ;;
  esac
  databricks workspace get-status "$dest_dir/$relative" -o json | jq -r '"present: \(.path) (\(.object_type))"'
done
