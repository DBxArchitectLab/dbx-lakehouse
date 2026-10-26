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

## Set up (once)

### 1. Create the service principal

Databricks account console → **User management → Service principals → Add service principal** →
`sp-dbx-lakehouse`. It needs no account role. On the service principal → **Credentials & secrets → Generate
secret**; copy the **Client ID** (its application ID) and the **Secret** now.

Put the application ID in `databricks.yml`, in `run_as.service_principal_name` of the `uat` and `prod` targets.

### 2. Give it access to uat and prod

Account console → **Workspaces** → for **uat** and **prod** → **Permissions → Add permissions** → `sp-dbx-lakehouse`
→ **User**. It doesn't need workspace admin: it creates its own jobs and owns them. It needs no access to dev.

### 3. Grant it its catalogs, in the infrastructure repository

The catalogs' grants are managed by Terraform in `dbx-platform-infra-azure`, and those grants are authoritative: a
grant made by hand would be removed by the next bootstrap apply. So add the service principal there:

1. In `dbx-platform-infra-azure`, `live/uat/workspace-bootstrap/catalog-config.yaml` and
   `live/prod/workspace-bootstrap/catalog-config.yaml`, add the application ID to `catalog.grant_principals`. The
   default privileges (`BROWSE`, `USE_CATALOG`, `CREATE_SCHEMA`) are what the bundle needs: it creates the
   `lakehouse` schema and owns it.
2. Run `uat-dbxarchitectlab-workspace-bootstrap` and `prod-dbxarchitectlab-workspace-bootstrap` with plan, then
   apply.

### 4. Check serverless compute for jobs

The jobs run on serverless compute; it must be enabled for the account (account console → **Settings → Feature
enablement**).

### 5. Create the GitHub environments

GitHub → this repository → **Settings → Environments**:

| Environment | Secrets | Protection |
| --- | --- | --- |
| `uat` | `DATABRICKS_CLIENT_ID` (the application ID), `DATABRICKS_CLIENT_SECRET` (the OAuth secret) | **Deployment branches:** `main` only |
| `prod` | The same two secrets | **Required reviewers** (the approval before prod), **Deployment branches:** `main` only |

The workspace URLs are in `databricks.yml`; the workflows don't need them as secrets.

### 6. Merge to `main`

The first merge runs the Deploy workflow: tests, uat (deploy and a smoke run of `sample-ingest`), then it waits for
approval and deploys prod. Check uat: **Workflows** shows `sample-ingest`, owned by `sp-dbx-lakehouse`, and
`dbxarchitectlab_uat.lakehouse` has two tables.

## Develop

Everything happens in dev, as yourself (you need `USE CATALOG` and `CREATE SCHEMA` on `dbxarchitectlab_dev`, which
`DBX_Architect_Lab_Admin` members have):

```bash
databricks auth login --host https://adb-7405609089943919.19.azuredatabricks.net

databricks bundle validate -t dev
databricks bundle deploy -t dev          # your own copy: [dev <you>] sample-ingest, schema dev_<you>_lakehouse
databricks bundle run -t dev sample_ingest
databricks bundle destroy -t dev         # when you are done with the copy

pip install pytest && pytest -q tests    # unit tests, no workspace needed
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

## Contributing and license

Issues and pull requests are welcome.
