# dbx-lakehouse-ai-bi

Part of **DBX Architect Lab**, an enterprise Databricks platform built in public:
[YouTube](https://www.youtube.com/@DBxArchitectLab) ·
[LinkedIn](https://www.linkedin.com/in/DBxArchitectLab) ·
[GitHub](https://github.com/DBxArchitectLab)

Data engineering and AI work on the Azure Databricks platform, packaged as a Databricks Asset Bundle. Work is built
in **dev** and deployed to **dev**, **uat** and **prod** by GitHub Actions: automatically from `main`, or on demand from
any branch you pick. Nobody deploys a shared copy by hand.

| Repository | Owns |
| --- | --- |
| `dbx-platform-infra-azure` | The workspaces, networking, catalogs and storage this repo deploys into |
| `dbx-lakehouse-ai-bi` (this one) | Pipelines, jobs, AI and BI assets, promoted dev → uat → prod |
| `dbx-governance` | Account-level governance and audit across all workspaces |

## Environments

| Target | Workspace | Catalog | Deployed by | Runs as |
| --- | --- | --- | --- | --- |
| `dev` | `https://adb-7405609089943919.19.azuredatabricks.net` | `dbxarchitectlab_dev` | Each developer, from their machine | The developer |
| `dev-shared` | the dev workspace | `dbxarchitectlab_dev` | GitHub Actions, **Run workflow → dev**, any branch | `sp-dbx-lakehouse` |
| `uat` | `https://adb-7405605496889455.15.azuredatabricks.net` | `dbxarchitectlab_uat` | GitHub Actions, on merge to `main`, or **Run workflow → uat** from any branch | `sp-dbx-lakehouse` |
| `prod` | `https://adb-7405604784566671.11.azuredatabricks.net` | `dbxarchitectlab_prod` | GitHub Actions, after uat on merge to `main`, or **Run workflow → prod** from `main`; always after an approval | `sp-dbx-lakehouse` |

- **dev** uses development mode: every developer gets their own copy. Jobs are prefixed `[dev <user>]`, schedules
  are paused, and the schema is `dev_<user>_lakehouse`, so nobody overwrites anyone else's tables.
- **dev-shared**, **uat** and **prod** use production mode: one shared copy per environment, under
  `/Workspace/Users/<sp-dbx-lakehouse application ID>/.bundle/` (the service principal's own folder, which other
  users can't write to), owned and run by `sp-dbx-lakehouse`, with `DBX_Architect_Lab_Admin` able to manage it.
  In dev-shared the schedules are paused: it runs when the pipeline (or you) starts it. Its schema is `lakehouse`,
  next to the developers' `dev_<user>_lakehouse` schemas.

## Layout

```
databricks.yml                  The bundle: variables and the dev, uat and prod targets
resources/                      What gets deployed: one resource per file (*.job.yml, *.schema.yml, ...)
src/identity/, src/jobs/        Workspace-local group migration (see Identity below); unit tested
config/group_migration.yaml     Its configuration
src/notebooks/shared/           Notebooks for people to run by hand; copied to /Workspace/Shared (see below)
scripts/deploy-shared-notebooks.sh  Copies src/notebooks/shared to /Workspace/Shared; run by the pipeline
scripts/put-migration-secrets.sh   Stores the group migration's account credentials in dev, uat and prod (once)
tests/                          Unit tests (no Databricks connection needed)
.github/workflows/ci.yml        Pull requests: tests, and the bundle validated against uat
.github/workflows/cd.yml        Jobs dev, uat, prod. Merge to main: uat → approval → prod;
                                Run workflow: only the job of the environment you choose, from the branch you choose
```

The `lakehouse` schema is the bundle's place for its tables. Add real work as resources next to it, and keep each
environment's differences in the targets and variables of `databricks.yml`, never in the code.

### Shared notebooks

Everything under `src/notebooks/shared/` is copied to **`/Workspace/Shared/`** in the target workspace, subfolders
included, by each deployment of dev (the shared copy), uat and prod. It is excluded from the bundle's own folder, so
there is one copy. Use it for notebooks people run by hand, not for job code.

- Same name: overwritten. Removed from the folder: **not** deleted from the workspace; delete it there by hand.
- `/Workspace/Shared` is writable by all workspace users: keep secrets and credentials out of these notebooks.
- Developers' own dev deployments (`bundle deploy -t dev`) don't copy it. To try a change in dev, run
  `bash scripts/deploy-shared-notebooks.sh dev` (it copies to dev's `/Workspace/Shared`, as you; needs `jq`).

| Notebook | What it does | Run as |
| --- | --- | --- |
| `create_workspace_level_group` | Creates the workspace-local groups `test_local_group_<env>` and `test_local_nested_group_<env>` (dev, uat or prod) with the workspace Groups API, nests the second in the first and adds you to the second, for testing the group migration (see [Identity](#identity-workspace-local-groups-to-account-groups)). `env` = `auto` detects the workspace; re-running is safe | A workspace admin |

## One-time setup

Done once, by a Databricks account admin together with someone who can change the GitHub repository and run the
`dbx-platform-infra-azure` workflow. Afterwards, merges to `main` deploy on their own. Steps 1-5 prepare the platform,
6-7 GitHub and this repository, 8 checks everything before the first merge, and 9 is the first deployment.

### Before you start

| Check | How |
| --- | --- |
| dev, uat and prod workspaces exist, with their catalogs `dbxarchitectlab_dev`, `_uat`, `_prod` | `dbx-platform-infra-azure` workspace and workspace-bootstrap stacks applied for each environment |
| You are a Databricks **account admin** | The account console (`https://accounts.azuredatabricks.net`) shows **User management** and **Workspaces** |
| You can run the `dbx-platform-infra-azure` workflow | Its Actions tab, **Terragrunt Deploy Stacks → Run workflow** |
| You are an admin of this GitHub repository | **Settings** is visible |
| Databricks CLI 0.230 or later, and Python 3.11 | `databricks --version`, `python --version` |

### 1. Create the service principal `sp-dbx-lakehouse`

The identity that deploys to dev (the shared copy), uat and prod, and that the jobs run as there. Its own, not shared with the
infrastructure or governance pipelines, so each can be granted, rotated and audited on its own.

1. Account console → **User management → Service principals → Add service principal**.
2. Choose **Databricks managed**, name it `sp-dbx-lakehouse`, and add it. It needs **no account role**.
3. Open it and copy the **Application ID** (a UUID). This is its "client ID" everywhere below.
4. **Credentials & secrets → Generate secret** (OAuth secret). Copy the **Secret** now; it is shown once. Note its
   expiry date in your calendar: it has to be rotated before then (see [Maintenance](#maintenance)).

### 2. Give it access to dev, uat and prod

Account console → **Workspaces** → for **dev**, **uat** and **prod** → **Permissions → Add permissions** →
`sp-dbx-lakehouse` → **User** → **Save**.

User is enough: the service principal creates its own jobs and schema and owns them.

### 3. Grant it the dev, uat and prod catalogs, in the infrastructure repository

The catalogs and their grants are managed by Terraform in `dbx-platform-infra-azure`, and those grants are
authoritative: a grant made by hand in the workspace would be removed by the next bootstrap apply. So the grant goes
into that repository's configuration:

1. In `dbx-platform-infra-azure`, edit `catalog-config.yaml` in `live/dev/workspace-bootstrap/`,
   `live/uat/workspace-bootstrap/` and `live/prod/workspace-bootstrap/`, and add the application ID:

   ```yaml
   catalog:
     name: "dbxarchitectlab_uat"            # dbxarchitectlab_dev / _prod in the other files
     grant_principals:
       - "DBX_Architect_Lab_Admin"
       - "dbxarchitectlab@gmail.com"
       - "9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
   ```

   The default privileges, `BROWSE`, `USE_CATALOG` and `CREATE_SCHEMA`, are exactly what this bundle needs: it
   creates the `lakehouse` schema, owns it, and so can create tables in it.
2. Merge that change, then run its workflow: `uat-dbxarchitectlab-workspace-bootstrap` **plan** (expect only the
   catalog grants to change), then **apply**; the same for `dev-dbxarchitectlab-workspace-bootstrap` and
   `prod-dbxarchitectlab-workspace-bootstrap`.
3. Check in each workspace: **Catalog → `dbxarchitectlab_<env>` → Permissions** lists `sp-dbx-lakehouse`.

### 4. Check serverless compute for jobs

The jobs have no cluster definition, so they run on serverless compute. Account console → **Settings → Feature
enablement**: serverless compute must be on. (Without it, each job task needs a `job_cluster` instead.)

### 5. Make sure developers can work in dev

Developers deploy their own copy to dev as themselves. They need `USE CATALOG` and `CREATE SCHEMA` on
`dbxarchitectlab_dev`; members of `DBX_Architect_Lab_Admin` have them. For anyone else, add them (or their group)
to `grant_principals` in `live/dev/workspace-bootstrap/catalog-config.yaml`, as in step 3.

### 6. Put the application ID in the bundle

In `databricks.yml`, the `dev-shared`, `uat` and `prod` targets run as the service principal's application ID
(already set for `sp-dbx-lakehouse`; change all three if the service principal is ever replaced):

```yaml
    run_as:
      service_principal_name: "9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
```

`service_principal_name` takes the **application ID**, not the display name: with the name, deploy fails because no
service principal has that ID.

### 7. Create the GitHub environments

GitHub → this repository → **Settings → Environments → New environment**, three times:

| Environment | Secrets | Protection rules |
| --- | --- | --- |
| `dev` | `DATABRICKS_CLIENT_ID` = the application ID; `DATABRICKS_CLIENT_SECRET` = the OAuth secret | **Deployment branches and tags:** no restriction (any branch can go to dev) |
| `uat` | The same two secrets | **Deployment branches and tags:** no restriction (any branch can go to uat; pull requests also validate against it). Optionally, required reviewers |
| `prod` | The same two secrets | **Required reviewers:** the people who approve prod releases. **Deployment branches and tags:** selected branches, `main` |

- The environment names must be exactly `dev`, `uat` and `prod`: the **Run workflow** choice is the environment name.
- prod is held to `main` twice: by its branch rule here, and by a check in the workflow.
- The CI workflow also uses the `uat` environment's secrets, to validate pull requests against uat.
- The workspace URLs are in `databricks.yml`, so they aren't secrets.
- Paste the secret carefully: a trailing space or newline makes sign-in fail.

Optionally, protect `main` (**Settings → Branches → Add rule**): require a pull request and the `CI` checks before
merging, so nothing reaches uat without review.

### 8. Check everything before the first merge

From your machine, sign in **as the service principal** and validate the three targets it deploys. This proves the
ID, the secret, the workspace access and the bundle, without waiting for a workflow:

```bash
export DATABRICKS_CLIENT_ID="<application ID>"
export DATABRICKS_CLIENT_SECRET="<OAuth secret>"
export DATABRICKS_AUTH_TYPE=oauth-m2m

databricks bundle validate -t dev-shared
databricks bundle validate -t uat
databricks bundle validate -t prod

unset DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET DATABRICKS_AUTH_TYPE
```

Each should end with `Validation OK!` and show the workspace host of that target. Then validate dev as yourself:
`databricks auth login --host https://adb-7405609089943919.19.azuredatabricks.net` and
`databricks bundle validate -t dev`.

### 9. First deployment

1. Commit the change from step 6 on a branch, open a pull request, and check that **CI** passes (tests and the uat
   validation).
2. Merge it. The **Deploy** workflow starts: uat (validate and deploy), then it waits for a prod reviewer.
3. Check uat before approving: **Workflows** shows the bundle's jobs (`identity-workspace-group-migration`,
   `identity-local-group-drift-check`), owned by `sp-dbx-lakehouse`; **Catalog → `dbxarchitectlab_uat`** has the
   `lakehouse` schema.
4. Approve the prod deployment in the workflow run. Check prod the same way.
5. Try an on-demand deployment: **Actions → Deploy → Run workflow**, branch `main`, environment `dev`. dev now has the
   same jobs owned by `sp-dbx-lakehouse` (not prefixed `[dev ...]`), and `dbxarchitectlab_dev` has the `lakehouse`
   schema.

The setup is done. From now on, every merge to `main` goes through the same path, and any branch can be deployed on
demand (see [Deploy on demand](#deploy-on-demand)).

### Troubleshooting the setup

| Error | Cause | Fix |
| --- | --- | --- |
| `default auth: cannot configure default credentials` | The secrets aren't reaching the CLI, or the auth type isn't fixed | Check both secrets exist in the GitHub environment; the workflows set `DATABRICKS_AUTH_TYPE: oauth-m2m` |
| `invalid_client` / `Client authentication failed` | Wrong client ID or secret, or a secret from the Azure portal (Entra ID) instead of Databricks | Use the Databricks OAuth secret from step 1; re-paste both secrets |
| `... is not a member of this workspace` / 403 on deploy | Step 2 not done for that workspace | Add `sp-dbx-lakehouse` as **User** in dev, uat and prod |
| `run_as ... service principal ... not found` | The display name instead of the application ID in `databricks.yml` | Step 6 |
| `PERMISSION_DENIED: User does not have USE CATALOG / CREATE SCHEMA` | Step 3 not applied, or applied only in one environment | Add the application ID to `grant_principals`, plan and apply that bootstrap |
| The grant disappears after an infrastructure run | It was granted by hand | Grant it through `catalog-config.yaml` (step 3) |
| Serverless compute is not enabled | Step 4 | Enable it, or give the job tasks a `job_cluster` |
| Deploy waits forever on prod | Nobody has approved | A reviewer of the `prod` environment approves the run |
| `prod deploys only from main` / `Branch "..." is not allowed to deploy to prod` | Run workflow to prod from another branch | Merge to `main` first, then deploy `main` |
| `Branch "..." is not allowed to deploy to dev` (or uat) | That environment still has a branch rule | Step 7: no restriction for `dev` and `uat` |

## Set up as a developer (once per person)

1. Install the [Databricks CLI](https://docs.databricks.com/dev-tools/cli/install.html) (0.230 or later) and Python
   3.11; optionally the Databricks extension for VS Code.
2. Sign in to dev, once; the CLI keeps the login:

   ```bash
   databricks auth login --host https://adb-7405609089943919.19.azuredatabricks.net
   ```

3. Clone the repository and run `pip install pytest && pytest -q tests`.
4. `databricks bundle validate -t dev` should succeed. If it reports `CREATE SCHEMA` or `USE CATALOG` missing, see
   setup step 5.

You never need access to uat or prod to develop: they are deployed by the pipeline.

## Develop

Everything happens in dev, as yourself:

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev          # your own copy: [dev <you>] jobs, schema dev_<you>_lakehouse
databricks bundle run -t dev <job key>   # e.g. identity_group_migration
databricks bundle destroy -t dev         # when you are done with the copy

pytest -q tests                          # unit tests, no workspace needed
```

To try your branch as the service principal, in the shared copy, before a pull request: deploy it on demand to dev
(or uat), see [Deploy on demand](#deploy-on-demand).

Then open a pull request. CI runs the tests and validates the bundle against uat. After review, merge to `main`:
the Deploy workflow promotes it.

## Promotion

```
feature branch ──PR──▶ CI: tests + validate (uat)
      │
    merge
      ▼
main ──▶ uat: validate, deploy ──▶ approval ──▶ prod: validate, deploy
```

- A failed uat deployment stops the promotion: prod is not touched.
- prod waits for a reviewer of the `prod` GitHub environment.
- Only one deployment runs at a time; a newer merge waits for the running one.
- To roll back, revert the commit on `main`; the revert is promoted the same way.

## Deploy on demand

**Actions → Deploy → Run workflow**:

1. **Use workflow from:** the branch to deploy.
2. **Environment:** `dev`, `uat` or `prod`.

| Environment | Branches | Job that runs |
| --- | --- | --- |
| `dev` | Any | `dev`: the `dev-shared` target, validate, deploy |
| `uat` | Any | `uat`: validate, deploy |
| `prod` | `main` only | `prod`: a prod reviewer approves, then validate, deploy |

The Deploy workflow doesn't run the unit tests: CI runs them on every pull request, before anything is merged. A
branch deployed on demand without a pull request hasn't been tested, so run `pytest -q tests` first.

- dev and uat each hold **one** shared copy: deploying a branch replaces what was there, including what `main`
  deployed to uat. The next merge to `main` puts `main` back in uat; to restore it sooner, run the workflow from
  `main` for that environment.
- A deployment to one environment never touches the others, and on-demand runs don't continue to prod.
- One deployment per environment at a time: a second one for the same environment waits for the first (a third
  replaces the waiting one). Deployments to different environments run in parallel.

## Identity: workspace-local groups to account groups

Workspace-local groups live in one workspace only. Unity Catalog can't grant to them, the account can't see or
audit them, and the same name can mean different people in dev and prod. Account groups fix all three: one
definition, assigned to the workspaces that need it, usable in Unity Catalog grants.

The `identity-workspace-group-migration` job is deployed to dev, uat and prod like every other job here, and each
copy migrates **the workspace it runs in**. That keeps every workspace call inside its own workspace: serverless
compute can't call another workspace's API unless the account's network policy allows cross-workspace access. For
each workspace-local group, it:

1. **Account group:** creates one, named by `naming.template` in `config/group_migration.yaml` (default
   `{group}_{env}`, the environment from the bundle target). It only reuses an account group that it created itself
   in an earlier run (the registry table), or that the config lists in `adopt_account_groups`.
2. **Members:** the same users (by userName), service principals (by applicationId) and nested groups. Nested
   workspace-local groups are migrated first, and their account groups are added instead; if a nested group is
   blocked, every group that contains it is blocked too.
3. **Name clash:** if the account group has the local group's own name, the local group is renamed to
   `db-temp-<name>` first.
4. **Workspace access:** assigns the account group to the workspace (USER) and copies the local group's
   entitlements.
5. **Permissions:** moves the local group's permissions on workspace objects (clusters, jobs, notebooks, folders,
   SQL warehouses, ...) to the account group with the permission migration API.
6. **Clean-up:** deletes the local group, only in a run with `delete_local_groups = true`.

Every step is idempotent, so a failed run can be repeated. Problems (an identity missing at the account, a nested
group cycle or a blocked nested group, an account group that exists but wasn't created by the migration) are
reported, and that group is skipped in apply mode.

| File | What it is |
| --- | --- |
| `src/identity/group_migration.py` | The migration: inventory, naming, conflicts, nested-group order, the steps above |
| `src/identity/inventory.py` | The inventory tables |
| `src/jobs/migrate_workspace_groups.py` | The job entry point |
| `config/group_migration.yaml` | Naming, exclusions, adoptions, where the account credentials are |
| `resources/identity_group_migration.job.yml` | The migration job (on demand) |
| `resources/identity_local_group_drift.job.yml` | The daily drift check |

### One account group per workspace, never shared

Account groups are account-wide. If dev's, uat's and prod's `data_engineers` became one account group, everyone in
dev's group would gain prod's permissions. So the naming template **must** contain `{env}`: the same local group name
in three workspaces always becomes three account groups (`data_engineers_dev`, `data_engineers_uat`,
`data_engineers_prod`). The job refuses to start with a template that lacks `{group}` or `{env}`.

### Inventory tables

Every run (plan and apply) appends to four Delta tables in the environment's own catalog, schema `identity`
(`dbxarchitectlab_dev.identity`, `dbxarchitectlab_uat.identity`, `dbxarchitectlab_prod.identity`; created on the
first run):

| Table | One row per | Use it for |
| --- | --- | --- |
| `local_groups` | local group per run | The inventory: account group, member count, nested local groups, entitlements, status (`planned`, `migrated`, `local_group_deleted`, `blocked`), problems |
| `local_group_members` | member per local group per run | Who was in each local group when it was migrated |
| `migration_actions` | step per group per run | The audit trail: what was planned or done, in order |
| `account_group_registry` | account group the migration created | Which account groups the migration owns and may reuse |

Apply needs these tables (it reads the registry), so run it as the Databricks job.

### Set up the migration (once)

The job runs as `sp-dbx-lakehouse`. Creating account groups and assigning them to workspaces are account
operations, and moving permissions and changing groups are workspace-admin operations, so for this job
`sp-dbx-lakehouse` needs more than the deployment does:

1. **Account admin:** account console → **User management → Service principals → `sp-dbx-lakehouse` → Roles** →
   **Account admin**. Anyone who can change this repository's jobs (and deploy a branch to dev) can then act with
   account-admin rights through it: keep the repository's write access and the `prod` reviewers to the platform team.
2. **Workspace admin in dev, uat and prod:** in `dbx-platform-infra-azure`, add its application ID to
   `live/<env>/workspace-bootstrap/workspace-admin-config.yaml` for dev, uat and prod, then plan and apply each
   `<env>-dbxarchitectlab-workspace-bootstrap`.
3. **Its account credentials, in each of dev, uat and prod:** the account API can't use the job's own identity, so
   the job signs in to the account with `sp-dbx-lakehouse`'s client ID and OAuth secret and the account ID, all three
   read from the workspace's `sct_dbx_architect_lab` scope (`sp-dbx-lakehouse-client-id`,
   `sp-dbx-lakehouse-client-secret`, `databricks-account-id`). As a workspace admin of dev, uat and prod, in Git Bash:

   ```bash
   bash scripts/put-migration-secrets.sh
   ```

   It asks for the account ID and the OAuth secret once (hidden), signs in to each workspace in the browser, stores
   the three secrets, gives `sp-dbx-lakehouse` READ on the scope and lists the keys. Paste each value on its own;
   pasting several lines at once into the prompt goes wrong.

   Use the same Databricks OAuth secret as the GitHub environments (one-time setup step 1), and rotate it in both
   places (see [Maintenance](#maintenance)).
4. **Catalog:** nothing to do. `sp-dbx-lakehouse` already has `CREATE SCHEMA` on each environment's catalog (one-time
   setup step 3) and creates the `identity` schema on the first run.
5. Deploy (merge to `main`, or **Run workflow** for dev): the two jobs appear in each workspace.

The drift check's schedule is paused (`pause_status: PAUSED` in `resources/identity_local_group_drift.job.yml`): it
fails every day while local groups exist. Set it to `UNPAUSED` once the migration is finished.

### Run it

In each workspace, run `identity-workspace-group-migration` (**Run now with different parameters**):

| Run | Where | `mode` | `delete_local_groups` |
| --- | --- | --- | --- |
| 1. Review what would change | dev, uat, prod | `plan` | `false` |
| 2. Migrate dev | dev | `apply` | `false` |
| 3. Check dev: users still reach their jobs, clusters, notebooks and warehouses | | | |
| 4. Migrate uat, then prod | uat, then prod | `apply` | `false` |
| 5. Remove the local groups, once checked | dev, then uat, prod | `apply` | `true` |

Plan mode changes nothing in the workspace or the account. The output lists every local group, its account group,
its nested local groups and each action (`WOULD ...`), plus any problem to fix first; the same goes into the
inventory tables. Test groups: `src/notebooks/shared/create_workspace_level_group` creates `test_local_group_<env>`
with the nested group `test_local_nested_group_<env>` in it; plan lists the nested group under the parent's nested
local groups and migrates it first.

### What it doesn't cover

- **Unity Catalog grants:** none to migrate, since Unity Catalog never accepted workspace-local groups. Grant the new
  account groups where needed.
- **Legacy Hive metastore table ACLs:** check them separately if the workspaces used table access control.
- **Who should be in a group:** the job copies membership as it is. Review it before prod.

### Keeping it that way

`identity-local-group-drift-check`, once unpaused, runs daily in uat and prod (paused in dev) in plan mode and fails, with an email,
when any workspace-local group exists. Longer term, make Microsoft Entra ID the source of account groups (SCIM
provisioning or automatic identity management), so groups are managed once, in Entra ID, and only assigned to
workspaces.

## Maintenance

- **Rotate the OAuth secret** before it expires: account console → `sp-dbx-lakehouse` → **Credentials & secrets →
  Generate secret**, update `DATABRICKS_CLIENT_SECRET` in the `dev`, `uat` and `prod` GitHub environments and
  `sp-dbx-lakehouse-client-secret` in each workspace's `sct_dbx_architect_lab` scope (`bash
  scripts/put-migration-secrets.sh`), then delete the old secret.
- **Add a reviewer for prod:** **Settings → Environments → prod → Required reviewers**.
- **Remove a developer's dev copy:** they run `databricks bundle destroy -t dev`, or a workspace admin deletes their
  `[dev <user>]` jobs and `dev_<user>_lakehouse` schema.

## Contributing and license

Issues and pull requests are welcome.
