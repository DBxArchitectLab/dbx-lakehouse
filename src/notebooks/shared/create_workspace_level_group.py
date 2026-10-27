# Databricks notebook source
# MAGIC %md
# MAGIC # Create workspace-level groups
# MAGIC Creates workspace-local groups with the workspace Groups API (`/api/2.0/preview/scim/v2/Groups`), for testing the
# MAGIC workspace-local to account group migration (`identity-workspace-group-migration`). Groups created in the
# MAGIC workspace UI are account groups; only this API creates a local one.
# MAGIC
# MAGIC | Group | Members |
# MAGIC | --- | --- |
# MAGIC | `test_local_group_<env>` | `test_local_nested_group_<env>` (a nested group) |
# MAGIC | `test_local_nested_group_<env>` | You, the user running the notebook |
# MAGIC
# MAGIC The nested group tests the migration's nested-group handling: it migrates `test_local_nested_group_<env>` first,
# MAGIC then adds its account group to the account group of `test_local_group_<env>`.
# MAGIC
# MAGIC - Run it as a **workspace admin**: only admins can create groups.
# MAGIC - `env` = `auto` takes the environment from the workspace this runs in; pick one to override it.
# MAGIC - Safe to re-run: existing groups and members are reported, not created again.

# COMMAND ----------

from databricks.sdk import WorkspaceClient
from databricks.sdk.service import iam

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
nested_group_name = f"test_local_nested_group_{env}"
print(f"Environment: {env}; groups: {group_name}, {nested_group_name}")

# COMMAND ----------


def ensure_local_group(name: str) -> str:
    """The ID of the group with this name, created if it doesn't exist yet."""
    existing = list(w.groups.list(filter=f'displayName eq "{name}"', attributes="id,displayName"))
    if existing:
        group_id = existing[0].id
        print(f"{name} already exists (id {group_id}); nothing created.")
    else:
        group_id = w.groups.create(display_name=name).id
        print(f"Created {name} (id {group_id}).")

    # WorkspaceGroup = workspace-local; Group = an account group assigned to this workspace.
    group = w.groups.get(group_id)
    resource_type = group.meta.resource_type if group.meta else None
    print(f"  Type: {resource_type}")
    if resource_type != "WorkspaceGroup":
        print(f"  Warning: {name} is not workspace-local, so the group migration will not pick it up.")
    return group_id


def ensure_member(group_id: str, group: str, member_id: str, member: str) -> None:
    """Adds the member (a user, service principal or group) to the group, unless it is already in it."""
    if any(m.value == member_id for m in w.groups.get(group_id).members or []):
        print(f"{member} is already a member of {group}.")
        return
    w.groups.patch(
        group_id,
        schemas=[iam.PatchSchema.URN_IETF_PARAMS_SCIM_API_MESSAGES_2_0_PATCH_OP],
        operations=[iam.Patch(op=iam.PatchOp.ADD, path="members", value=[{"value": member_id}])],
    )
    print(f"Added {member} to {group}.")


group_id = ensure_local_group(group_name)
nested_group_id = ensure_local_group(nested_group_name)

# COMMAND ----------

# The nested group goes into the parent; you go into the nested group, so it has a member to migrate.
me = w.current_user.me()
ensure_member(group_id, group_name, nested_group_id, nested_group_name)
ensure_member(nested_group_id, nested_group_name, me.id, me.user_name)

for gid, name in ((group_id, group_name), (nested_group_id, nested_group_name)):
    members = w.groups.get(gid).members or []
    print(f"{name}: {', '.join(m.display or m.value for m in members) or 'no members'}")
