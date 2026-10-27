"""The job entry point, run in plan mode against fake clients: it migrates the workspace it runs in."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS

from test_group_migration import FakeAccount, FakeWorkspace, group

ROOT = Path(__file__).resolve().parents[1]


def load_job():
    spec = importlib.util.spec_from_file_location("migrate_job", ROOT / "src" / "jobs" / "migrate_workspace_groups.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_migrates_the_workspace_it_runs_in(monkeypatch, capsys):
    job = load_job()
    w = FakeWorkspace([group("1", "engineers", members=[("Users/7", "7", "u")])])
    w.get_workspace_id = lambda: 7405609089943919
    w.config = NS(host="https://adb-7405609089943919.19.azuredatabricks.net")
    w.current_user = NS(me=lambda: NS(user_name="9a769c8e-a44b-4009-9378-719753df14c7"))
    a = FakeAccount(users={"user7@example.com": "u7"})
    monkeypatch.setattr(job, "WorkspaceClient", lambda: w)
    monkeypatch.setattr(job, "AccountClient", lambda **_: a)
    monkeypatch.setattr(job, "spark_session", lambda: None)
    for name in ("DATABRICKS_CLIENT_SECRET",):
        monkeypatch.setenv(name, "x")
    monkeypatch.setattr("sys.argv", ["job", "--config", str(ROOT / "config" / "group_migration.yaml"),
                                     "--env", "dev", "--catalog", "dbxarchitectlab_dev"])

    assert job.main() == 0
    out = capsys.readouterr().out
    assert "Workspace 7405609089943919" in out and "environment dev" in out
    assert "[dev] engineers -> engineers_dev" in out and "PLANNED" in out
    assert a.calls == [] and w.calls == []  # plan mode changes nothing
