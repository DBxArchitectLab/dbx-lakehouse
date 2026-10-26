# dbx-lakehouse-ai-bi

Part of **DBX Architect Lab**, an enterprise Databricks platform built in public:
[YouTube](https://www.youtube.com/@DBxArchitectLab) ·
[LinkedIn](https://www.linkedin.com/in/DBxArchitectLab) ·
[GitHub](https://github.com/DBxArchitectLab)

Data engineering and AI work on the Azure Databricks platform, packaged as a Databricks Asset Bundle. Work is built
in **dev** and promoted to **uat** and **prod** by GitHub Actions; nobody deploys to uat or prod by hand.

| Repository | Owns |
| --- | --- |
| `dbx-platform-infra-azure` | The workspaces, networking, catalogs and storage this repo deploys into |
| `dbx-lakehouse-ai-bi` (this one) | Pipelines, jobs, AI and BI assets, promoted dev → uat → prod |
| `dbx-governance` | Account-level governance and audit across all workspaces |

## Environments

| Target | Workspace | Catalog | Deployed by | Runs as |
| --- | --- | --- | --- | --- |
| `dev` | `https://adb-7405609089943919.19.azuredatabricks.net` | `dbxarchitectlab_dev` | Each developer, from their machine | The developer |
| `uat` | `https://adb-7405605496889455.15.azuredatabricks.net` | `dbxarchitectlab_uat` | GitHub Actions, on merge to `main` | `sp-dbx-lakehouse` |
| `prod` | `https://adb-7405604784566671.11.azuredatabricks.net` | `dbxarchitectlab_prod` | GitHub Actions, after uat and an approval | `sp-dbx-lakehouse` |

- **dev** uses development mode: every developer gets their own copy. Jobs are prefixed `[dev <user>]`, schedules
  are paused, and the schema is `dev_<user>_lakehouse`, so nobody overwrites anyone else's tables.
- **uat** and **prod** use production mode: one shared copy per environment, under `/Workspace/Shared/.bundle/`,
  owned and run by `sp-dbx-lakehouse`, with `DBX_Architect_Lab_Admin` able to manage it.

## Layout

```
databricks.yml                  The bundle: variables and the dev, uat and prod targets
resources/                      What gets deployed: one resource per file (*.job.yml, *.schema.yml, ...)
src/lakehouse/                  Python code the notebooks import; unit tested
src/notebooks/                  Notebooks that the jobs run
tests/                          Unit tests (no Databricks connection needed)
.github/workflows/ci.yml        Pull requests: tests, and the bundle validated against uat
.github/workflows/cd.yml        Merge to main: tests → uat (deploy and smoke run) → approval → prod
```

The starter resources, a `lakehouse` schema and a `sample-ingest` job that writes two small tables, prove the path
end to end. Replace them with real work, and keep each environment's differences in the targets and variables of
`databricks.yml`, never in the code.

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

The identity that deploys to uat and prod and that the jobs run as there. Its own, not shared with the
infrastructure or governance pipelines, so each can be granted, rotated and audited on its own.

1. Account console → **User management → Service principals → Add service principal**.
2. Choose **Databricks managed**, name it `sp-dbx-lakehouse`, and add it. It needs **no account role**.
3. Open it and copy the **Application ID** (a UUID). This is its "client ID" everywhere below.
4. **Credentials & secrets → Generate secret** (OAuth secret). Copy the **Secret** now; it is shown once. Note its
   expiry date in your calendar: it has to be rotated before then (see [Maintenance](#maintenance)).

### 2. Give it access to uat and prod

Account console → **Workspaces** → for **uat**, then **prod** → **Permissions → Add permissions** →
`sp-dbx-lakehouse` → **User** → **Save**.

User is enough: the service principal creates its own jobs and schema and owns them. It needs no access to dev,
because nothing is deployed there automatically.

### 3. Grant it the uat and prod catalogs, in the infrastructure repository

The catalogs and their grants are managed by Terraform in `dbx-platform-infra-azure`, and those grants are
authoritative: a grant made by hand in the workspace would be removed by the next bootstrap apply. So the grant goes
into that repository's configuration:

1. In `dbx-platform-infra-azure`, edit `live/uat/workspace-bootstrap/catalog-config.yaml` and
   `live/prod/workspace-bootstrap/catalog-config.yaml`, and add the application ID:

   ```yaml
   catalog:
     name: "dbxarchitectlab_uat"            # dbxarchitectlab_prod in the prod file
     grant_principals:
       - "DBX_Architect_Lab_Admin"
       - "dbxarchitectlab@gmail.com"
       - "9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
   ```

   The default privileges, `BROWSE`, `USE_CATALOG` and `CREATE_SCHEMA`, are exactly what this bundle needs: it
   creates the `lakehouse` schema, owns it, and so can create tables in it.
2. Merge that change, then run its workflow: `uat-dbxarchitectlab-workspace-bootstrap` **plan** (expect only the
   catalog grants to change), then **apply**; the same for `prod-dbxarchitectlab-workspace-bootstrap`.
3. Check in each workspace: **Catalog → `dbxarchitectlab_uat` → Permissions** lists `sp-dbx-lakehouse`.

### 4. Check serverless compute for jobs

The jobs have no cluster definition, so they run on serverless compute. Account console → **Settings → Feature
enablement**: serverless compute must be on. (Without it, each job task needs a `job_cluster` instead.)

### 5. Make sure developers can work in dev

Developers deploy their own copy to dev as themselves. They need `USE CATALOG` and `CREATE SCHEMA` on
`dbxarchitectlab_dev`; members of `DBX_Architect_Lab_Admin` have them. For anyone else, add them (or their group)
to `grant_principals` in `live/dev/workspace-bootstrap/catalog-config.yaml`, as in step 3.

### 6. Put the application ID in the bundle

In `databricks.yml`, **both** the `uat` and `prod` targets run as the service principal's application ID (already set
for `sp-dbx-lakehouse`; change both if the service principal is ever replaced):

```yaml
    run_as:
      service_principal_name: "9a769c8e-a44b-4009-9378-719753df14c7"   # sp-dbx-lakehouse
```

`service_principal_name` takes the **application ID**, not the display name: with the name, deploy fails because no
service principal has that ID.

### 7. Create the GitHub environments

GitHub → this repository → **Settings → Environments → New environment**, twice:

| Environment | Secrets | Protection rules |
| --- | --- | --- |
| `uat` | `DATABRICKS_CLIENT_ID` = the application ID; `DATABRICKS_CLIENT_SECRET` = the OAuth secret | **Deployment branches and tags:** selected branches, `main` |
| `prod` | The same two secrets | **Required reviewers:** the people who approve prod releases. **Deployment branches and tags:** `main` |

- The CI workflow also uses the `uat` environment's secrets, to validate pull requests against uat.
- The workspace URLs are in `databricks.yml`, so they aren't secrets.
- Paste the secret carefully: a trailing space or newline makes sign-in fail.

Optionally, protect `main` (**Settings → Branches → Add rule**): require a pull request and the `CI` checks before
merging, so nothing reaches uat without review.

### 8. Check everything before the first merge

From your machine, sign in **as the service principal** and validate both targets. This proves the ID, the secret,
the workspace access and the bundle in two commands, without waiting for a workflow:

```bash
export DATABRICKS_CLIENT_ID="<application ID>"
export DATABRICKS_CLIENT_SECRET="<OAuth secret>"
export DATABRICKS_AUTH_TYPE=oauth-m2m

databricks bundle validate -t uat
databricks bundle validate -t prod

unset DATABRICKS_CLIENT_ID DATABRICKS_CLIENT_SECRET DATABRICKS_AUTH_TYPE
```

Both should end with `Validation OK!` and show the workspace host of that target. Then validate dev as yourself:
`databricks auth login --host https://adb-7405609089943919.19.azuredatabricks.net` and
`databricks bundle validate -t dev`.

### 9. First deployment

1. Commit the change from step 6 on a branch, open a pull request, and check that **CI** passes (tests and the uat
   validation).
2. Merge it. The **Deploy** workflow starts: tests, then uat (validate, deploy, and a run of `sample-ingest`), then it
   waits for a prod reviewer.
3. Check uat before approving: **Workflows** shows `sample-ingest`, owned by `sp-dbx-lakehouse`, with a successful
   run; **Catalog → `dbxarchitectlab_uat` → `lakehouse`** has `sample_orders` and `sample_revenue_by_region`.
4. Approve the prod deployment in the workflow run. Check prod the same way (the job is deployed; its first run is the
   next scheduled one, or start it with **Run now**).

The setup is done. From now on, every merge to `main` goes through the same path.

### Troubleshooting the setup

| Error | Cause | Fix |
| --- | --- | --- |
| `default auth: cannot configure default credentials` | The secrets aren't reaching the CLI, or the auth type isn't fixed | Check both secrets exist in the GitHub environment; the workflows set `DATABRICKS_AUTH_TYPE: oauth-m2m` |
| `invalid_client` / `Client authentication failed` | Wrong client ID or secret, or a secret from the Azure portal (Entra ID) instead of Databricks | Use the Databricks OAuth secret from step 1; re-paste both secrets |
| `... is not a member of this workspace` / 403 on deploy | Step 2 not done for that workspace | Add `sp-dbx-lakehouse` as **User** in uat and prod |
| `run_as ... service principal ... not found` | The display name instead of the application ID in `databricks.yml` | Step 6 |
| `PERMISSION_DENIED: User does not have USE CATALOG / CREATE SCHEMA` | Step 3 not applied, or applied only in one environment | Add the application ID to `grant_principals`, plan and apply that bootstrap |
| The grant disappears after an infrastructure run | It was granted by hand | Grant it through `catalog-config.yaml` (step 3) |
| Serverless compute is not enabled | Step 4 | Enable it, or give the job tasks a `job_cluster` |
| Deploy waits forever on prod | Nobody has approved | A reviewer of the `prod` environment approves the run |

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
databricks bundle deploy -t dev          # your own copy: [dev <you>] sample-ingest, schema dev_<you>_lakehouse
databricks bundle run -t dev sample_ingest
databricks bundle destroy -t dev         # when you are done with the copy

pytest -q tests                          # unit tests, no workspace needed
```

Then open a pull request. CI runs the tests and validates the bundle against uat. After review, merge to `main`:
the Deploy workflow promotes it.

## Promotion

```
feature branch ──PR──▶ CI: tests + validate (uat)
      │
    merge
      ▼
main ──▶ tests ──▶ uat: validate, deploy, smoke run ──▶ approval ──▶ prod: validate, deploy
```

- A failed smoke run in uat stops the promotion: prod is not touched.
- prod waits for a reviewer of the `prod` GitHub environment.
- Only one deployment runs at a time; a newer merge waits for the running one.
- To roll back, revert the commit on `main`; the revert is promoted the same way.

## Maintenance

- **Rotate the OAuth secret** before it expires: account console → `sp-dbx-lakehouse` → **Credentials & secrets →
  Generate secret**, update `DATABRICKS_CLIENT_SECRET` in both GitHub environments, then delete the old secret.
- **Add a reviewer for prod:** **Settings → Environments → prod → Required reviewers**.
- **Remove a developer's dev copy:** they run `databricks bundle destroy -t dev`, or a workspace admin deletes their
  `[dev <user>]` jobs and `dev_<user>_lakehouse` schema.

## Contributing and license

Issues and pull requests are welcome.
