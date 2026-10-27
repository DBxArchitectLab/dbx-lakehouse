"""Job entry point: migrate (or report) the workspace-local groups of the workspace this job runs in.

The bundle deploys the job to dev, uat and prod, so each environment migrates its own groups: the workspace calls
stay inside the workspace (serverless compute can't call other workspaces' APIs without cross-workspace network
rules), and only the account API is called from outside.

  --env dev|uat|prod             the environment of this workspace: used in the account group names ({env})
  --catalog, --schema            where the inventory tables are (the environment's catalog, schema identity)
  --mode plan                    read only: list every workspace-local group and what apply would do (default)
  --mode apply                   carry out the migration (see identity.group_migration)
  --delete-local-groups true     also delete the local groups (a separate run, after checking the result)
  --fail-on-local-groups true    exit non-zero when any workspace-local group exists (the scheduled drift check)

Every run writes the inventory tables (identity.inventory). Apply needs them: the account group registry is what tells
the job which account groups it may reuse.

Identity: sp-dbx-lakehouse. Workspace calls use the job's own identity (run_as). Account calls (create account
groups, assign them to the workspace) need its OAuth client ID and secret and the account ID, from the secret scope in
the config. Outside Databricks, the workspace comes from the usual CLI/SDK settings and the account credentials from
DATABRICKS_CLIENT_ID, DATABRICKS_CLIENT_SECRET and DATABRICKS_ACCOUNT_ID; there, plan mode works without the tables
and only prints.
"""
import argparse
import inspect
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from databricks.sdk import AccountClient, WorkspaceClient

# src/ on the path, so identity imports. Not from __file__: a spark_python_task on serverless runs this file through
# exec(), which doesn't define it; the code object still carries the file's path.
sys.path.insert(0, str(Path(inspect.currentframe().f_code.co_filename).resolve().parents[1]))
from identity import group_migration as gm  # noqa: E402
from identity.inventory import Inventory, status  # noqa: E402

ENVIRONMENTS = ("dev", "uat", "prod")


def secret(scope: str, key: str, env: str) -> str:
    try:
        from databricks.sdk.runtime import dbutils
        return dbutils.secrets.get(scope, key)
    except Exception:  # not on Databricks
        value = os.environ.get(env)
        if not value:
            sys.exit(f"Missing credential: secret {scope}/{key} or environment variable {env}")
        return value


def spark_session():
    try:
        from pyspark.sql import SparkSession
        return SparkSession.builder.getOrCreate()
    except Exception:
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--env", required=True, choices=ENVIRONMENTS)
    ap.add_argument("--catalog", required=True)
    ap.add_argument("--schema", default="identity")
    ap.add_argument("--mode", choices=["plan", "apply"], default="plan")
    ap.add_argument("--delete-local-groups", default="false")
    ap.add_argument("--fail-on-local-groups", default="false")
    args = ap.parse_args()
    dry_run = args.mode == "plan"
    delete_local = args.delete_local_groups.lower() == "true"

    cfg = yaml.safe_load(Path(args.config).read_text())
    naming = cfg["naming"]
    try:
        gm.validate_template(naming["template"])
    except ValueError as e:
        sys.exit(str(e))

    run_id, run_at = str(uuid.uuid4()), datetime.now(timezone.utc)
    spark = spark_session()
    inv = Inventory(spark, args.catalog, args.schema) if spark else None
    if inv is None and not dry_run:
        sys.exit("apply needs the inventory tables (run it as the Databricks job): the account group registry is "
                 "how the migration knows which account groups it created")
    if inv:
        inv.ensure_tables()
    owned = inv.owned_account_groups() if inv else set()
    adopt = set(cfg.get("adopt_account_groups") or [])

    creds = cfg["credentials"]
    a = AccountClient(host=cfg["account_host"],
                      account_id=secret(creds["scope"], creds["account_id_key"], "DATABRICKS_ACCOUNT_ID"),
                      client_id=secret(creds["scope"], creds["client_id_key"], "DATABRICKS_CLIENT_ID"),
                      client_secret=secret(creds["scope"], creds["client_secret_key"], "DATABRICKS_CLIENT_SECRET"))

    # The workspace this job runs in, as the job's own identity.
    w = WorkspaceClient()
    ws = gm.Workspace(args.env, int(w.get_workspace_id()), w.config.host)
    print(f"Workspace {ws.workspace_id} ({ws.host}), environment {ws.env}, as {w.current_user.me().user_name}")

    exclude = set(cfg.get("exclude_groups") or [])
    plans = gm.inventory(w, ws, naming["template"], exclude, naming["temp_prefix"])
    gm.check_conflicts(plans)

    def registered(plan: gm.GroupPlan, gid: str) -> None:
        inv.register(plan, gid, run_id, run_at)
        owned.add(plan.target_name)

    index = gm.AccountIndex(a)
    try:
        ordered = gm.dependency_order(plans)
        target_of = {p.local_name: p.target_name for p in ordered}
        blocked_names = set()
        for p in ordered:
            for child in p.nested_local_groups:
                if child in blocked_names and not any(child in x for x in p.problems):
                    p.problems.append(f"nested local group {child!r} is blocked; migrate it first")
            if p.blocked and not dry_run:
                blocked_names.add(p.local_name)
                continue
            gm.apply(a, w, p, index, target_of, dry_run=dry_run, delete_local_groups=delete_local,
                     temp_prefix=naming["temp_prefix"], owned=owned, adopt=adopt, on_created=registered)
            if p.blocked:
                blocked_names.add(p.local_name)
    finally:
        if inv and plans:
            inv.write_run(plans, run_id, run_at, args.mode)

    for p in plans:
        print(f"\n[{p.env}] {p.local_name} -> {p.target_name}  ({len(p.members)} members, "
              f"nested local groups: {', '.join(p.nested_local_groups) or 'none'}, "
              f"entitlements: {', '.join(p.entitlements) or 'none'})  {status(p, args.mode).upper()}")
        for act in p.actions:
            print(f"    {'WOULD ' if dry_run else ''}{act.step}: {act.detail}")
        for line in p.problems:
            print(f"    PROBLEM {line}")
    blocked = [p for p in plans if p.blocked]
    print(f"\nRun {run_id}: {len(plans)} workspace-local group(s) in {ws.env}, mode {args.mode}, "
          f"{len(blocked)} blocked." + (f" Inventory: {inv.prefix}." if inv else ""))

    if blocked and not dry_run:
        return 1
    if args.fail_on_local_groups.lower() == "true" and plans:
        print("Workspace-local groups found: migrate them to account groups.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
