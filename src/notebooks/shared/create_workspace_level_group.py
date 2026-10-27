# Databricks notebook source
# MAGIC %md
# MAGIC # Create a workspace-level group
# MAGIC Creates the workspace-local group `test_local_group_<env>` (dev, uat or prod) with the workspace Groups API
# MAGIC (`/api/2.0/preview/scim/v2/Groups`), for testing the workspace-local to account group migration in
# MAGIC `dbx-governance`. Groups created in the workspace UI are account groups; only this API creates a local one.
# MAGIC
# MAGIC - Run it as a **workspace admin**: only admins can create groups.
# MAGIC - `env` = `auto` takes the environment from the workspace this runs in; pick one to override it.
# MAGIC - Safe to re-run: an existing group is reported, not created again.

# COMMAND ----------

from databricks.sdk import WorkspaceClient

ENVIRONMENTS = ("dev", "uat", "prod")
# Workspace ID -> environment, from the dbx-platform-infra-azure workspace stacks.
WORKSPACE_ENVIRONMENTS = {
    "7405609089943919": "dev",
    "7405605496889455": "uat",
    "7405604784566671": "prod",
}

dbutils.widgets.dropdown("env", "auto", ["auto", *ENVIRONMENTS], "Environment")  # noqa: F821 (provided by Databricks)
w = WorkspaceClient()

env = dbutils.widgets.get("env")  # noqa: F821
if env == "auto":
    workspace_id = str(w.get_workspace_id())
    env = WORKSPACE_ENVIRONMENTS.get(workspace_id)
    if env is None:
        raise ValueError(f"Workspace {workspace_id} is not dev, uat or prod; choose env in the widget.")
if env not in ENVIRONMENTS:
    raise ValueError(f"env must be one of {', '.join(ENVIRONMENTS)}, not {env!r}.")

group_name = f"test_local_group_{env}"
print(f"Environment: {env}; group: {group_name}")

# COMMAND ----------

existing = list(w.groups.list(filter=f'displayName eq "{group_name}"', attributes="id,displayName"))
if existing:
    group_id = existing[0].id
    print(f"{group_name} already exists (id {group_id}); nothing created.")
else:
    group_id = w.groups.create(display_name=group_name).id
    print(f"Created {group_name} (id {group_id}).")

# WorkspaceGroup = workspace-local; Group = an account group assigned to this workspace.
group = w.groups.get(group_id)
resource_type = group.meta.resource_type if group.meta else None
print(f"Type: {resource_type}")
if resource_type != "WorkspaceGroup":
    print(f"Warning: {group_name} is not workspace-local, so the group migration will not pick it up.")
