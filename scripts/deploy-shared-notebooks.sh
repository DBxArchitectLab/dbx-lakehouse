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

echo "Copying $source_dir to $dest_dir on $DATABRICKS_HOST"
databricks workspace import-dir "$source_dir" "$dest_dir" --overwrite
