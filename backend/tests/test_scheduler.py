"""Tests for per-config scheduler wiring.

Pytest and uvicorn run in different Python processes (even both in the same
container), so we query the live scheduler via /api/debug/scheduler rather
than importing the scheduler singleton directly.
"""

CFG_NAME = "__test_scheduler"


def _job_for(client, config_id: str) -> dict | None:
    state = client.get("/api/debug/scheduler").json()
    for job in state.get("jobs", []):
        if job["id"] == f"config-{config_id}":
            return job
    return None


def test_create_active_config_registers_job(client, clean_db):
    resp = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 3,
            "run_hour": 6,
            "active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    cfg = resp.json()
    job = _job_for(client, cfg["id"])
    assert job is not None, "job should be registered for active interval config"
    assert "interval" in job["trigger"].lower()
    client.delete(f"/api/configs/{cfg['id']}")


def test_create_weekdays_config_uses_cron_trigger(client, clean_db):
    resp = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "weekdays",
            "weekdays": [2, 4, 6],
            "run_hour": 6,
            "active": True,
        },
    )
    assert resp.status_code == 201, resp.text
    cfg = resp.json()
    job = _job_for(client, cfg["id"])
    assert job is not None
    trigger = job["trigger"].lower()
    assert "cron" in trigger
    assert "wed" in trigger and "fri" in trigger and "sun" in trigger
    client.delete(f"/api/configs/{cfg['id']}")


def test_inactive_config_has_no_job(client, clean_db):
    cfg = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 1,
            "active": False,
        },
    ).json()
    assert _job_for(client, cfg["id"]) is None
    client.delete(f"/api/configs/{cfg['id']}")


def test_patch_active_toggles_job(client, clean_db):
    cfg = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 1,
            "active": True,
        },
    ).json()
    assert _job_for(client, cfg["id"]) is not None

    client.patch(f"/api/configs/{cfg['id']}", json={"active": False})
    assert _job_for(client, cfg["id"]) is None

    client.patch(f"/api/configs/{cfg['id']}", json={"active": True})
    assert _job_for(client, cfg["id"]) is not None

    client.delete(f"/api/configs/{cfg['id']}")


def test_delete_config_removes_job(client, clean_db):
    cfg = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 1,
            "active": True,
        },
    ).json()
    assert _job_for(client, cfg["id"]) is not None
    client.delete(f"/api/configs/{cfg['id']}")
    assert _job_for(client, cfg["id"]) is None


def test_generate_endpoint_enqueues_job(client, clean_db):
    cfg = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 1,
        },
    ).json()
    client.post(f"/api/configs/{cfg['id']}/topics", json={"name": "AI/LLMs"})

    resp = client.post(f"/api/configs/{cfg['id']}/generate")
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"].startswith(f"issue-")
    assert body["status"] == "queued"
    assert body["issue_id"]  # endpoint creates and returns the Issue id synchronously

    client.delete(f"/api/configs/{cfg['id']}")


def test_manual_trigger_actually_runs_the_agent(client, clean_db):
    """End-to-end proof that APScheduler actually dispatches and executes
    the job, i.e. asyncio.run() from a threadpool context works."""
    import time

    cfg = client.post(
        "/api/configs",
        json={
            "name": CFG_NAME,
            "schedule_kind": "interval",
            "frequency_days": 1,
        },
    ).json()
    topic = client.post(f"/api/configs/{cfg['id']}/topics", json={"name": "AI/LLMs"}).json()
    client.post(
        f"/api/topics/{topic['id']}/feeds",
        json={"url": "https://hnrss.org/newest?q=LLM&count=5"},
    )

    resp = client.post(f"/api/configs/{cfg['id']}/generate").json()
    issue_id = resp["issue_id"]
    assert issue_id

    # Poll until the issue leaves pending/running or times out (5 min).
    deadline = time.time() + 300
    final = None
    while time.time() < deadline:
        issue = client.get(f"/api/issues/{issue_id}").json()
        if issue["status"] not in ("pending", "running"):
            final = issue
            break
        time.sleep(3)

    assert final is not None, "manual run stuck in pending/running past timeout"
    assert final["status"] in ("ready", "drafted", "failed"), final
    # Whatever the outcome, the pipeline should have done SOMETHING:
    # either rendered, drafted, or recorded an error.
    if final["status"] == "ready":
        assert final.get("html_path")

    client.delete(f"/api/configs/{cfg['id']}")
