import json
import os
import random
import sqlite3
import threading
import time
from urllib.parse import urlparse

from flask import Flask, jsonify, render_template, request, session, redirect, url_for
from flask_sock import Sock

from compare_utils import DEFAULT_COMPARE_ENDPOINTS, compare_endpoints
from form_filler import generate_entry_text, run_fill_session
from migrate_db import run as run_migrations


DEFAULT_BASELINE_URL = (
    "http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com/"
)

LABS = {
    "lab1": {
        "id": "lab1",
        "code": "Lab 1",
        "title": "Zero-Downtime Migration",
        "status": "Active",
        "summary": "Migrate safely, keep data in sync, and verify parity against a baseline.",
        "tagline": (
            "Deploy the app, run an expand/backfill/cutover migration, and verify "
            "your data matches the baseline."
        ),
        "compare_enabled": True,
        "automation_enabled": True,
        "leaderboard_enabled": True,
        "submission_enabled": True,
        "form_cta": "Run comparison",
        "form_helper": "Submit your app URL to compare against the baseline.",
        "sections": [
            {
                "title": "Core steps",
                "items": [
                    {"title": "Deploy", "body": "Launch your app on Kubernetes."},
                    {
                        "title": "Migrate",
                        "body": "Use expand/backfill/dual-write for zero downtime.",
                    },
                    {"title": "Submit", "body": "Register your app URL for checking."},
                    {
                        "title": "Verify",
                        "body": "Track sync status on the lab leaderboard.",
                    },
                ],
            },
            {
                "title": "Zero-downtime phases",
                "items": [
                    {"title": "Expand", "body": "Add new schema fields safely."},
                    {"title": "Backfill", "body": "Copy data without blocking traffic."},
                    {"title": "Dual-write", "body": "Keep old and new data in sync."},
                    {"title": "Cutover", "body": "Switch reads to the new schema."},
                ],
            },
            {
                "title": "Verifier endpoints",
                "items": [
                    {"title": "/api/moods/all", "body": "Mood entry parity."},
                    {"title": "/api/journal/entries/all", "body": "Journal entry parity."},
                    {"title": "/api/stats/overview", "body": "Aggregate stats parity."},
                    {"title": "/api/server/values/all", "body": "Server state parity."},
                ],
            },
        ],
    },
    "lab2": {
        "id": "lab2",
        "code": "Lab 2",
        "title": "Terraform Modules: Files Service + S3",
        "status": "Active",
        "summary": "Add a files microservice with S3 storage using reusable Terraform modules.",
        "tagline": (
            "Build a Terraform module that provisions S3 + IAM + IRSA and deploys the "
            "files-service into the existing app stack."
        ),
        "compare_enabled": False,
        "automation_enabled": False,
        "leaderboard_enabled": False,
        "submission_enabled": False,
        "form_cta": "Register endpoint",
        "form_helper": "No submissions required for Lab 2.",
        "sections": [
            {
                "title": "What you will build",
                "items": [
                    {
                        "title": "Terraform module",
                        "body": (
                            "Create a reusable module that provisions the files-service "
                            "stack: S3 bucket, IAM policy/role, IRSA service account, and "
                            "Kubernetes deployment/service/ingress."
                        ),
                    },
                    {
                        "title": "Automation ready",
                        "body": (
                            "The module must be callable from the root stack so new labs can "
                            "enable files-service automatically without manual kubectl steps."
                        ),
                    },
                    {
                        "title": "Target app",
                        "body": (
                            "Use the GratitudeApp repo as the base application: "
                            "https://github.com/UnpredictablePrashant/GratitudeApp."
                        ),
                    },
                ],
            },
            {
                "title": "Inputs you must expose",
                "items": [
                    {
                        "title": "S3 settings",
                        "body": "S3_BUCKET, S3_PREFIX, and AWS_REGION as module inputs.",
                    },
                    {
                        "title": "Cluster + namespace",
                        "body": "Cluster name/region, namespace, and OIDC provider details.",
                    },
                    {
                        "title": "Images",
                        "body": (
                            "Files service image tag (prashantdey/merndemoapp:fileservice1.0) "
                            "and UI image tag if managed in Terraform."
                        ),
                    },
                ],
            },
            {
                "title": "IAM + IRSA requirements",
                "items": [
                    {
                        "title": "IAM policy",
                        "body": (
                            "Allow s3:PutObject, s3:GetObject, and s3:ListBucket scoped to "
                            "your bucket and optional prefix."
                        ),
                    },
                    {
                        "title": "IRSA role",
                        "body": "Create an IAM role for service account files-service-sa.",
                    },
                    {
                        "title": "Service account",
                        "body": (
                            "Annotate files-service-sa with the role ARN and bind it in the "
                            "deployment."
                        ),
                    },
                ],
            },
            {
                "title": "Kubernetes resources",
                "items": [
                    {
                        "title": "Deployment",
                        "body": (
                            "Deploy files-service with env vars for S3_BUCKET, S3_PREFIX, "
                            "AWS_REGION and the IRSA service account."
                        ),
                    },
                    {
                        "title": "Service",
                        "body": "Create a ClusterIP service for internal routing.",
                    },
                    {
                        "title": "Ingress",
                        "body": "Route /api/files/* to the files-service.",
                    },
                ],
            },
            {
                "title": "Dev team additions (already built)",
                "items": [
                    {
                        "title": "Service",
                        "body": "Node/Express + AWS SDK + multer under /api/files/*.",
                    },
                    {
                        "title": "Images",
                        "body": (
                            "prashantdey/merndemoapp:fileservice1.0 and "
                            "prashantdey/merndemoapp:clientv1.0."
                        ),
                    },
                    {
                        "title": "Kubernetes",
                        "body": (
                            "files-service-deployment.yml, files-service-cluster-ip-service.yml, "
                            "ingress-service.yml with /api/files/*."
                        ),
                    },
                ],
            },
            {
                "title": "Apply order + validation",
                "items": [
                    {
                        "title": "DB fixes",
                        "body": "Apply postgres-init-config.yml and postgres-migrate-job.yml.",
                    },
                    {
                        "title": "Infra rollout",
                        "body": "Apply S3 + IAM + IRSA before the deployment.",
                    },
                    {
                        "title": "Success criteria",
                        "body": (
                            "Upload a file, list objects, and download from the UI. "
                            "Confirm the pod uses IRSA (no static AWS keys)."
                        ),
                    },
                ],
            },
        ],
    },
}


def list_labs():
    return [LABS[key] for key in sorted(LABS.keys())]


def get_lab(lab_id):
    return LABS.get(lab_id)


DEFAULT_LAB_ID = "lab1"
AUTOMATION_LAB_ID = "lab1"
COMPARE_LAB_ID = "lab1"


def parse_endpoints(raw_value):
    if not raw_value:
        return list(DEFAULT_COMPARE_ENDPOINTS)
    return [item.strip() for item in raw_value.split(",") if item.strip()]


def is_valid_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "lab1-default-secret")
sock = Sock(app)
clients = set()
active_fill_lock = threading.Lock()
fill_active = False
db_lock = threading.Lock()
automation_enabled = False
automation_paused_at = None
automation_total_paused_seconds = 0
next_auto_fill_at = None
next_auto_fill_entry_text = None
next_auto_fill_seed = None
last_auto_fill_wait_seconds = None

FILL_INTERVAL_SECONDS = int(os.environ.get("FILL_INTERVAL_SECONDS", "120"))
AUTO_INTERVAL_MIN_SECONDS = int(os.environ.get("AUTO_INTERVAL_MIN_SECONDS", "10"))
AUTO_INTERVAL_MAX_SECONDS = int(os.environ.get("AUTO_INTERVAL_MAX_SECONDS", "75"))
COMPARE_INTERVAL_SECONDS = int(os.environ.get("COMPARE_INTERVAL_SECONDS", "150"))
FILL_ITERATIONS = int(os.environ.get("FILL_ITERATIONS", "1"))
FILL_MODE = os.environ.get("FILL_MODE", "all")
DB_PATH = os.environ.get("DB_PATH", "app.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "lab1admin")


@app.get("/")
def index():
    return render_template("index.html", labs=list_labs())


@app.get("/lab1")
def lab1():
    return redirect(url_for("lab_detail", lab_id="lab1"))


@app.get("/lab2")
def lab2():
    return redirect(url_for("lab_detail", lab_id="lab2"))


@app.get("/labs/<lab_id>")
def lab_detail(lab_id):
    lab = get_lab(lab_id)
    if not lab:
        return "Lab not found.", 404
    return render_template(
        "lab_detail.html",
        lab=lab,
        labs=list_labs(),
        teams=list_teams(lab_id),
        compare_interval_seconds=COMPARE_INTERVAL_SECONDS,
    )


@app.get("/leaderboard")
def leaderboard_page():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return "Lab not found.", 404
    return render_template(
        "leaderboard.html",
        lab=lab,
        labs=list_labs(),
        compare_interval_seconds=COMPARE_INTERVAL_SECONDS,
    )


@app.get("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = (request.form.get("password") or "").strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(url_for("admin_panel"))
        return render_template("admin.html", error="Invalid credentials.")
    return render_template("admin.html")


@app.get("/admin/panel")
def admin_panel():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        lab = get_lab(DEFAULT_LAB_ID)
        lab_id = lab["id"]
    paused_seconds = automation_total_paused_seconds
    if automation_paused_at is not None:
        paused_seconds += int(time.time() - automation_paused_at)
    next_fill_in = None
    if next_auto_fill_at is not None:
        next_fill_in = max(0, int(next_auto_fill_at - time.time()))
    return render_template(
        "admin_panel.html",
        lab=lab,
        labs=list_labs(),
        automation_enabled=automation_enabled,
        auto_interval_min=AUTO_INTERVAL_MIN_SECONDS,
        auto_interval_max=AUTO_INTERVAL_MAX_SECONDS,
        teams=list_teams(lab_id),
        submissions=list_students(lab_id),
        automation_paused_seconds=paused_seconds,
        next_fill_in_seconds=next_fill_in,
        next_fill_entry_text=next_auto_fill_entry_text,
        baseline_url=get_setting("baseline_url", DEFAULT_BASELINE_URL),
    )


@app.post("/admin/toggle")
def admin_toggle():
    global automation_enabled, automation_paused_at, automation_total_paused_seconds
    global next_auto_fill_at, next_auto_fill_entry_text, next_auto_fill_seed
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    automation_enabled = not automation_enabled
    now = int(time.time())
    if not automation_enabled:
        automation_paused_at = now
        next_auto_fill_at = None
        next_auto_fill_entry_text = None
        next_auto_fill_seed = None
        broadcast_fill_meta()
        broadcast("fill_log", {"message": f"Automation paused at {time.ctime(now)}."})
    else:
        if automation_paused_at is not None:
            paused_for = now - automation_paused_at
            automation_total_paused_seconds += paused_for
            broadcast(
                "fill_log",
                {
                    "message": (
                        f"Automation resumed after {paused_for}s paused "
                        f"(total paused {automation_total_paused_seconds}s)."
                    )
                },
            )
        automation_paused_at = None
        broadcast_fill_meta()
    return redirect(url_for("admin_panel", lab=lab_id))


def broadcast_fill_meta():
    if not automation_enabled:
        broadcast(
            "fill_meta",
            {"next_in_seconds": None, "entry_text": None, "status": "paused"},
        )
        return
    if next_auto_fill_at is None:
        broadcast(
            "fill_meta",
            {"next_in_seconds": None, "entry_text": None, "status": "pending"},
        )
        return
    next_in = max(0, int(next_auto_fill_at - time.time()))
    broadcast(
        "fill_meta",
        {
            "next_in_seconds": next_in,
            "entry_text": next_auto_fill_entry_text,
            "status": "scheduled",
        },
    )


@app.post("/admin/interval")
def admin_interval_update():
    global AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    min_value = (request.form.get("auto_interval_min") or "").strip()
    max_value = (request.form.get("auto_interval_max") or "").strip()
    try:
        min_seconds = int(min_value)
        max_seconds = int(max_value)
    except ValueError:
        return redirect(url_for("admin_panel", lab=lab_id))
    if min_seconds < 1 or max_seconds < 1 or min_seconds > max_seconds:
        return redirect(url_for("admin_panel", lab=lab_id))
    AUTO_INTERVAL_MIN_SECONDS = min_seconds
    AUTO_INTERVAL_MAX_SECONDS = max_seconds
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/teams")
def admin_team_create():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not get_lab(lab):
        lab = DEFAULT_LAB_ID
    if not lab or not name or not members:
        return redirect(url_for("admin_panel", lab=lab or DEFAULT_LAB_ID))
    create_team(lab, name, members)
    return redirect(url_for("admin_panel", lab=lab))


@app.post("/admin/teams/<int:team_id>/update")
def admin_team_update(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not get_lab(lab):
        lab = DEFAULT_LAB_ID
    if not lab or not name or not members:
        return redirect(url_for("admin_panel", lab=lab or DEFAULT_LAB_ID))
    update_team(team_id, lab, name, members)
    return redirect(url_for("admin_panel", lab=lab))


@app.post("/admin/teams/<int:team_id>/delete")
def admin_team_delete(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    delete_team(team_id)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/baseline")
def admin_baseline_update():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    baseline_url = (request.form.get("baseline_url") or "").strip()
    if not is_valid_url(baseline_url):
        return redirect(url_for("admin_panel", lab=lab_id))
    set_setting("baseline_url", baseline_url)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/submissions/delete")
def admin_submission_delete():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab_id = (request.form.get("lab") or DEFAULT_LAB_ID).strip().lower()
    if not get_lab(lab_id):
        lab_id = DEFAULT_LAB_ID
    target_url = (request.form.get("url") or "").strip()
    if not target_url:
        return redirect(url_for("admin_panel", lab=lab_id))
    delete_submission(lab_id, target_url)
    return redirect(url_for("admin_panel", lab=lab_id))


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting(key, fallback=None):
    with db_lock:
        conn = get_db()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
        finally:
            conn.close()
    return row["value"] if row else fallback


def set_setting(key, value):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, now),
            )
            conn.commit()
        finally:
            conn.close()


def init_db():
    run_migrations()
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    lab TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    added_at INTEGER NOT NULL,
                    PRIMARY KEY (lab, url)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    lab TEXT NOT NULL,
                    url TEXT NOT NULL,
                    name TEXT NOT NULL,
                    last_checked INTEGER,
                    sync INTEGER,
                    PRIMARY KEY (lab, url)
                )
                """
            )
            conn.commit()
        finally:
            conn.close()


def list_teams(lab=None):
    with db_lock:
        conn = get_db()
        try:
            if lab:
                rows = conn.execute(
                    """
                    SELECT id, lab, name, members, updated_at
                    FROM teams
                    WHERE lab = ?
                    ORDER BY name ASC
                    """,
                    (lab,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, lab, name, members, updated_at
                    FROM teams
                    ORDER BY lab ASC, name ASC
                    """
                ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def create_team(lab, name, members):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO teams (lab, name, members, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (lab, name, members, now, now),
            )
            conn.commit()
        finally:
            conn.close()


def update_team(team_id, lab, name, members):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                UPDATE teams
                SET lab = ?, name = ?, members = ?, updated_at = ?
                WHERE id = ?
                """,
                (lab, name, members, now, team_id),
            )
            conn.commit()
        finally:
            conn.close()


def delete_team(team_id):
    with db_lock:
        conn = get_db()
        try:
            conn.execute("DELETE FROM teams WHERE id = ?", (team_id,))
            conn.commit()
        finally:
            conn.close()


def upsert_student(lab_id, name, url):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO students (lab, url, name, added_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name,
                    added_at=excluded.added_at
                """,
                (lab_id, url, name, now),
            )
            conn.commit()
        finally:
            conn.close()


def list_students(lab_id=None):
    with db_lock:
        conn = get_db()
        try:
            if lab_id:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, added_at
                    FROM students
                    WHERE lab = ?
                    ORDER BY added_at DESC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, added_at
                    FROM students
                    ORDER BY added_at DESC
                    """
                ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def ensure_leaderboard_entry(lab_id, target_url, name):
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (lab, url, name, last_checked, sync)
                VALUES (?, ?, ?, NULL, NULL)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name
                """,
                (lab_id, target_url, name),
            )
            conn.commit()
        finally:
            conn.close()


def delete_submission(lab_id, target_url):
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                "DELETE FROM students WHERE lab = ? AND url = ?",
                (lab_id, target_url),
            )
            conn.execute(
                "DELETE FROM leaderboard WHERE lab = ? AND url = ?",
                (lab_id, target_url),
            )
            conn.commit()
        finally:
            conn.close()


def update_leaderboard(lab_id, target_url, name, sync_status):
    now = int(time.time())
    sync_value = 1 if sync_status is True else 0 if sync_status is False else None
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (lab, url, name, last_checked, sync)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(lab, url) DO UPDATE SET
                    name=excluded.name,
                    last_checked=excluded.last_checked,
                    sync=excluded.sync
                """,
                (lab_id, target_url, name, now, sync_value),
            )
            conn.commit()
        finally:
            conn.close()


def list_leaderboard(lab_id=None):
    with db_lock:
        conn = get_db()
        try:
            if lab_id:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, last_checked, sync
                    FROM leaderboard
                    WHERE lab = ?
                    ORDER BY COALESCE(last_checked, 0) DESC
                    """,
                    (lab_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT lab, name, url, last_checked, sync
                    FROM leaderboard
                    ORDER BY COALESCE(last_checked, 0) DESC
                    """
                ).fetchall()
        finally:
            conn.close()
    items = []
    for row in rows:
        sync_value = None
        if row["sync"] is not None:
            sync_value = bool(row["sync"])
        items.append(
            {
                "lab": row["lab"],
                "name": row["name"],
                "url": row["url"],
                "last_checked": row["last_checked"],
                "sync": sync_value,
            }
        )
    return items


@app.post("/api/compare")
def compare():
    global fill_active
    payload = request.get_json(silent=True) or {}
    name = (payload.get("name") or "").strip()
    target_url = (payload.get("url") or "").strip()
    lab_id = (payload.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    baseline_url = (payload.get("baseline_url") or "").strip() or os.environ.get(
        "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
    )

    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    if not name:
        return jsonify({"error": "Name is required."}), 400
    if not target_url:
        return jsonify({"error": "App URL is required."}), 400
    if not is_valid_url(target_url):
        return jsonify({"error": "App URL must include http or https."}), 400
    if lab["compare_enabled"] and not is_valid_url(baseline_url):
        return jsonify({"error": "Baseline URL is invalid."}), 500

    upsert_student(lab_id, name, target_url)
    ensure_leaderboard_entry(lab_id, target_url, name)

    if not lab["compare_enabled"]:
        return jsonify(
            {
                "name": name,
                "target_url": target_url,
                "status": "registered",
                "compare_enabled": False,
            }
        )

    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    started_at = time.time()
    ok, results = compare_endpoints(baseline_url, target_url, endpoints)
    elapsed_ms = int((time.time() - started_at) * 1000)
    update_leaderboard(lab_id, target_url, name, ok)

    with active_fill_lock:
        if not fill_active:
            fill_active = True
            shared_seed = int(time.time())
            job_payload = {
                "url": target_url,
                "baseline_url": baseline_url,
                "iterations": 1,
                "mode": FILL_MODE,
                "min_wait": 1,
                "max_wait": 2,
                "headless": True,
                "seed": shared_seed,
                "entry_mode": "local",
                "entry_text": generate_entry_text("local", seed=shared_seed),
                "target_name": name,
            }
            broadcast("fill_start", {"message": f"New app detected. Filling {target_url}."})
            thread = threading.Thread(target=run_fill_job, args=(job_payload,), daemon=True)
            thread.start()

    return jsonify(
        {
            "name": name,
            "baseline_url": baseline_url,
            "target_url": target_url,
            "status": "match" if ok else "mismatch",
            "elapsed_ms": elapsed_ms,
            "results": results,
            "compare_enabled": True,
        }
    )


@app.get("/api/students")
def students():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    return jsonify({"students": list_students(lab_id)})


def broadcast(event, payload):
    message = json.dumps({"event": event, "payload": payload})
    stale = []
    for ws in clients:
        try:
            ws.send(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        clients.discard(ws)


@sock.route("/ws")
def ws_handler(ws):
    clients.add(ws)
    try:
        while ws.receive() is not None:
            pass
    finally:
        clients.discard(ws)


def run_fill_job(payload):
    global fill_active
    try:
        baseline_url = payload.get("baseline_url")
        entry_text = payload.get("entry_text")
        if baseline_url:
            if entry_text:
                broadcast(
                    "fill_log",
                    {"message": f"[baseline] entry: {entry_text}"},
                )
            try:
                run_fill_session(
                    url=baseline_url,
                    mode=payload["mode"],
                    iterations=payload["iterations"],
                    min_wait=payload["min_wait"],
                    max_wait=payload["max_wait"],
                    headless=payload["headless"],
                    seed=payload["seed"],
                    entry_mode=payload["entry_mode"],
                    entry_text=entry_text,
                    log_cb=lambda message: broadcast(
                        "fill_log", {"message": f"[baseline] {message}"}
                    ),
                )
            except Exception as exc:
                broadcast(
                    "fill_error",
                    {"message": f"Auto-fill failed for baseline ({baseline_url}): {exc}"},
                )
                return
            broadcast(
                "fill_log",
                {"message": f"[baseline] fill completed for {baseline_url}"},
            )
        try:
            if entry_text:
                broadcast(
                    "fill_log",
                    {
                        "message": (
                            f"[{payload.get('target_name', 'target')}] "
                            f"{payload['url']} entry: {entry_text}"
                        )
                    },
                )
            run_fill_session(
                url=payload["url"],
                mode=payload["mode"],
                iterations=payload["iterations"],
                min_wait=payload["min_wait"],
                max_wait=payload["max_wait"],
                headless=payload["headless"],
                seed=payload["seed"],
                entry_mode=payload["entry_mode"],
                entry_text=entry_text,
                log_cb=lambda message: broadcast(
                    "fill_log", {"message": f"[target] {message}"}
                ),
            )
        except Exception as exc:
            broadcast(
                "fill_error",
                {"message": f"Auto-fill failed for target ({payload['url']}): {exc}"},
            )
            return
        target_label = payload.get("target_name") or "target"
        broadcast(
            "fill_log",
            {"message": f"[{target_label}] fill completed for {payload['url']}"},
        )
        broadcast("fill_done", {"message": "Form filling complete."})
    except Exception as exc:
        broadcast("fill_error", {"message": f"Form filling failed: {exc}"})
    finally:
        with active_fill_lock:
            fill_active = False


@app.get("/api/leaderboard")
def get_leaderboard():
    lab_id = (request.args.get("lab") or DEFAULT_LAB_ID).strip().lower()
    lab = get_lab(lab_id)
    if not lab:
        return jsonify({"error": "Unknown lab."}), 400
    return jsonify({"leaderboard": list_leaderboard(lab_id)})

def compare_and_update(lab_id, target_url, name, baseline_url):
    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    ok, _results = compare_endpoints(baseline_url, target_url, endpoints)
    update_leaderboard(lab_id, target_url, name, ok)
    return ok


def run_fill_loop():
    global fill_active, next_auto_fill_at, next_auto_fill_entry_text, next_auto_fill_seed
    global last_auto_fill_wait_seconds
    while True:
        if not automation_enabled:
            next_auto_fill_at = None
            next_auto_fill_entry_text = None
            next_auto_fill_seed = None
            broadcast_fill_meta()
            time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))
            continue
        baseline_url = os.environ.get(
            "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
        )
        if not is_valid_url(baseline_url):
            wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
            last_auto_fill_wait_seconds = wait_seconds
            next_auto_fill_at = time.time() + wait_seconds
            next_auto_fill_seed = int(next_auto_fill_at)
            next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
            broadcast_fill_meta()
            time.sleep(wait_seconds)
            continue

        with active_fill_lock:
            if fill_active:
                wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
                last_auto_fill_wait_seconds = wait_seconds
                next_auto_fill_at = time.time() + wait_seconds
                next_auto_fill_seed = int(next_auto_fill_at)
                next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
                broadcast_fill_meta()
                time.sleep(wait_seconds)
                continue
            fill_active = True

        try:
            broadcast("fill_start", {"message": "Auto-fill: baseline + student apps."})
            if next_auto_fill_entry_text is not None and next_auto_fill_seed is not None:
                shared_seed = next_auto_fill_seed
                entry_text = next_auto_fill_entry_text
            else:
                shared_seed = int(time.time())
                entry_text = generate_entry_text("local", seed=shared_seed)
            next_auto_fill_at = None
            next_auto_fill_entry_text = None
            next_auto_fill_seed = None
            broadcast_fill_meta()
            if entry_text:
                broadcast("fill_log", {"message": f"[baseline] entry: {entry_text}"})
            try:
                run_fill_session(
                    url=baseline_url,
                    mode=FILL_MODE,
                    iterations=FILL_ITERATIONS,
                    min_wait=1,
                    max_wait=2,
                    headless=True,
                    seed=shared_seed,
                    entry_mode="local",
                    entry_text=entry_text,
                    log_cb=lambda message: broadcast(
                        "fill_log", {"message": f"[baseline] {message}"}
                    ),
                )
            except Exception as exc:
                broadcast(
                    "fill_error",
                    {"message": f"Auto-fill failed for baseline ({baseline_url}): {exc}"},
                )
                continue

            students = list_students(AUTOMATION_LAB_ID)

            for student in students:
                url = student["url"]
                name = student["name"]
                if not is_valid_url(url):
                    update_leaderboard(AUTOMATION_LAB_ID, url, name, False)
                    broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                    continue
                broadcast("fill_log", {"message": f"[{name}] filling {url}"})
                try:
                    if entry_text:
                        broadcast(
                            "fill_log",
                            {"message": f"[{name}] entry: {entry_text}"},
                        )
                    run_fill_session(
                        url=url,
                        mode=FILL_MODE,
                        iterations=FILL_ITERATIONS,
                        min_wait=1,
                        max_wait=2,
                        headless=True,
                        seed=shared_seed,
                        entry_mode="local",
                        entry_text=entry_text,
                        log_cb=lambda message: broadcast(
                            "fill_log", {"message": f"[{name}] {message}"}
                        ),
                    )
                except Exception as exc:
                    broadcast(
                        "fill_error",
                        {"message": f"Auto-fill failed for {name} ({url}): {exc}"},
                    )
                    continue
                broadcast(
                    "fill_log",
                    {"message": f"[{name}] fill completed for {url}"},
                )
                compare_and_update(AUTOMATION_LAB_ID, url, name, baseline_url)
            broadcast("fill_done", {"message": "Auto-fill cycle complete."})
        except Exception as exc:
            broadcast("fill_error", {"message": f"Auto-fill failed: {exc}"})
        finally:
            with active_fill_lock:
                fill_active = False
        wait_seconds = random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS)
        last_auto_fill_wait_seconds = wait_seconds
        next_auto_fill_at = time.time() + wait_seconds
        next_auto_fill_seed = int(next_auto_fill_at)
        next_auto_fill_entry_text = generate_entry_text("local", seed=next_auto_fill_seed)
        broadcast_fill_meta()
        time.sleep(wait_seconds)


def run_compare_loop():
    while True:
        baseline_url = os.environ.get(
            "BASELINE_URL", get_setting("baseline_url", DEFAULT_BASELINE_URL)
        )
        if not is_valid_url(baseline_url):
            time.sleep(COMPARE_INTERVAL_SECONDS)
            continue
        students = list_students(COMPARE_LAB_ID)
        if students:
            broadcast(
                "fill_log",
                {"message": "Periodic check: validating submitted apps."},
            )
        for student in students:
            url = student["url"]
            name = student["name"]
            if not is_valid_url(url):
                update_leaderboard(COMPARE_LAB_ID, url, name, False)
                broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                continue
            compare_and_update(COMPARE_LAB_ID, url, name, baseline_url)
        time.sleep(COMPARE_INTERVAL_SECONDS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    init_db()
    thread = threading.Thread(target=run_fill_loop, daemon=True)
    thread.start()
    compare_thread = threading.Thread(target=run_compare_loop, daemon=True)
    compare_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False)
