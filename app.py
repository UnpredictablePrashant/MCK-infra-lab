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
from form_filler import run_fill_session
from migrate_db import run as run_migrations


DEFAULT_BASELINE_URL = (
    "http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com/"
)


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
automation_enabled = True

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
    return render_template("index.html")


@app.get("/lab1")
def lab1():
    return render_template("lab1.html", teams=list_teams("lab1"))


@app.get("/leaderboard")
def leaderboard_page():
    return render_template(
        "leaderboard.html", compare_interval_seconds=COMPARE_INTERVAL_SECONDS
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
    return render_template(
        "admin_panel.html",
        automation_enabled=automation_enabled,
        auto_interval_min=AUTO_INTERVAL_MIN_SECONDS,
        auto_interval_max=AUTO_INTERVAL_MAX_SECONDS,
        teams=list_teams(),
    )


@app.post("/admin/toggle")
def admin_toggle():
    global automation_enabled
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    automation_enabled = not automation_enabled
    return redirect(url_for("admin_panel"))


@app.post("/admin/interval")
def admin_interval_update():
    global AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    min_value = (request.form.get("auto_interval_min") or "").strip()
    max_value = (request.form.get("auto_interval_max") or "").strip()
    try:
        min_seconds = int(min_value)
        max_seconds = int(max_value)
    except ValueError:
        return redirect(url_for("admin_panel"))
    if min_seconds < 1 or max_seconds < 1 or min_seconds > max_seconds:
        return redirect(url_for("admin_panel"))
    AUTO_INTERVAL_MIN_SECONDS = min_seconds
    AUTO_INTERVAL_MAX_SECONDS = max_seconds
    return redirect(url_for("admin_panel"))


@app.post("/admin/teams")
def admin_team_create():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not lab or not name or not members:
        return redirect(url_for("admin_panel"))
    create_team(lab, name, members)
    return redirect(url_for("admin_panel"))


@app.post("/admin/teams/<int:team_id>/update")
def admin_team_update(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    lab = (request.form.get("lab") or "").strip().lower()
    name = (request.form.get("name") or "").strip()
    members = (request.form.get("members") or "").strip()
    if not lab or not name or not members:
        return redirect(url_for("admin_panel"))
    update_team(team_id, lab, name, members)
    return redirect(url_for("admin_panel"))


@app.post("/admin/teams/<int:team_id>/delete")
def admin_team_delete(team_id):
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    delete_team(team_id)
    return redirect(url_for("admin_panel"))


@app.post("/admin/submissions/delete")
def admin_submission_delete():
    if not session.get("admin"):
        return redirect(url_for("admin_login"))
    target_url = (request.form.get("url") or "").strip()
    if not target_url:
        return redirect(url_for("admin_panel"))
    delete_submission(target_url)
    return redirect(url_for("admin_panel"))


@app.post("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect(url_for("admin_login"))


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    run_migrations()
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS students (
                    url TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    added_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS leaderboard (
                    url TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    last_checked INTEGER,
                    sync INTEGER
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


def upsert_student(name, url):
    now = int(time.time())
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO students (url, name, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    name=excluded.name
                """,
                (url, name, now),
            )
            conn.commit()
        finally:
            conn.close()


def list_students():
    with db_lock:
        conn = get_db()
        try:
            rows = conn.execute(
                "SELECT name, url, added_at FROM students ORDER BY added_at DESC"
            ).fetchall()
        finally:
            conn.close()
    return [dict(row) for row in rows]


def ensure_leaderboard_entry(target_url, name):
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (url, name, last_checked, sync)
                VALUES (?, ?, NULL, NULL)
                ON CONFLICT(url) DO UPDATE SET
                    name=excluded.name
                """,
                (target_url, name),
            )
            conn.commit()
        finally:
            conn.close()


def delete_submission(target_url):
    with db_lock:
        conn = get_db()
        try:
            conn.execute("DELETE FROM students WHERE url = ?", (target_url,))
            conn.execute("DELETE FROM leaderboard WHERE url = ?", (target_url,))
            conn.commit()
        finally:
            conn.close()


def update_leaderboard(target_url, name, sync_status):
    now = int(time.time())
    sync_value = 1 if sync_status is True else 0 if sync_status is False else None
    with db_lock:
        conn = get_db()
        try:
            conn.execute(
                """
                INSERT INTO leaderboard (url, name, last_checked, sync)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    name=excluded.name,
                    last_checked=excluded.last_checked,
                    sync=excluded.sync
                """,
                (target_url, name, now, sync_value),
            )
            conn.commit()
        finally:
            conn.close()


def list_leaderboard():
    with db_lock:
        conn = get_db()
        try:
            rows = conn.execute(
                """
                SELECT name, url, last_checked, sync
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
    baseline_url = (payload.get("baseline_url") or "").strip() or os.environ.get(
        "BASELINE_URL", DEFAULT_BASELINE_URL
    )

    if not name:
        return jsonify({"error": "Name is required."}), 400
    if not target_url:
        return jsonify({"error": "App URL is required."}), 400
    if not is_valid_url(target_url):
        return jsonify({"error": "App URL must include http or https."}), 400
    if not is_valid_url(baseline_url):
        return jsonify({"error": "Baseline URL is invalid."}), 500

    upsert_student(name, target_url)
    ensure_leaderboard_entry(target_url, name)

    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    started_at = time.time()
    ok, results = compare_endpoints(baseline_url, target_url, endpoints)
    elapsed_ms = int((time.time() - started_at) * 1000)
    update_leaderboard(target_url, name, ok)

    with active_fill_lock:
        if not fill_active:
            fill_active = True
            job_payload = {
                "url": target_url,
                "iterations": 1,
                "mode": FILL_MODE,
                "min_wait": 1,
                "max_wait": 2,
                "headless": True,
                "seed": None,
                "entry_mode": "local",
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
        }
    )


@app.get("/api/students")
def students():
    return jsonify({"students": list_students()})


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
        run_fill_session(
            url=payload["url"],
            mode=payload["mode"],
            iterations=payload["iterations"],
            min_wait=payload["min_wait"],
            max_wait=payload["max_wait"],
            headless=payload["headless"],
            seed=payload["seed"],
            entry_mode=payload["entry_mode"],
            log_cb=lambda message: broadcast("fill_log", {"message": message}),
        )
        broadcast("fill_done", {"message": "Form filling complete."})
    except Exception as exc:
        broadcast("fill_error", {"message": f"Form filling failed: {exc}"})
    finally:
        with active_fill_lock:
            fill_active = False


@app.get("/api/leaderboard")
def get_leaderboard():
    return jsonify({"leaderboard": list_leaderboard()})


def compare_and_update(target_url, name, baseline_url):
    endpoints = parse_endpoints(os.environ.get("COMPARE_ENDPOINTS"))
    ok, _results = compare_endpoints(baseline_url, target_url, endpoints)
    update_leaderboard(target_url, name, ok)
    return ok


def run_fill_loop():
    global fill_active
    while True:
        if not automation_enabled:
            time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))
            continue
        baseline_url = os.environ.get("BASELINE_URL", DEFAULT_BASELINE_URL)
        if not is_valid_url(baseline_url):
            time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))
            continue

        with active_fill_lock:
            if fill_active:
                time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))
                continue
            fill_active = True

        try:
            broadcast("fill_start", {"message": "Auto-fill: baseline + student apps."})
            run_fill_session(
                url=baseline_url,
                mode=FILL_MODE,
                iterations=FILL_ITERATIONS,
                min_wait=1,
                max_wait=2,
                headless=True,
                seed=None,
                entry_mode="local",
                log_cb=lambda message: broadcast("fill_log", {"message": f"[baseline] {message}"}),
            )

            students = list_students()

            for student in students:
                url = student["url"]
                name = student["name"]
                if not is_valid_url(url):
                    update_leaderboard(url, name, False)
                    broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                    continue
                broadcast("fill_log", {"message": f"[{name}] filling {url}"})
                run_fill_session(
                    url=url,
                    mode=FILL_MODE,
                    iterations=FILL_ITERATIONS,
                    min_wait=1,
                    max_wait=2,
                    headless=True,
                    seed=None,
                    entry_mode="local",
                    log_cb=lambda message: broadcast("fill_log", {"message": f"[{name}] {message}"}),
                )
                compare_and_update(url, name, baseline_url)
            broadcast("fill_done", {"message": "Auto-fill cycle complete."})
        except Exception as exc:
            broadcast("fill_error", {"message": f"Auto-fill failed: {exc}"})
        finally:
            with active_fill_lock:
                fill_active = False
        time.sleep(random.randint(AUTO_INTERVAL_MIN_SECONDS, AUTO_INTERVAL_MAX_SECONDS))


def run_compare_loop():
    while True:
        baseline_url = os.environ.get("BASELINE_URL", DEFAULT_BASELINE_URL)
        if not is_valid_url(baseline_url):
            time.sleep(COMPARE_INTERVAL_SECONDS)
            continue
        students = list_students()
        if students:
            broadcast(
                "fill_log",
                {"message": "Periodic check: validating submitted apps."},
            )
        for student in students:
            url = student["url"]
            name = student["name"]
            if not is_valid_url(url):
                update_leaderboard(url, name, False)
                broadcast("fill_log", {"message": f"[{name}] invalid URL; skipped."})
                continue
            compare_and_update(url, name, baseline_url)
        time.sleep(COMPARE_INTERVAL_SECONDS)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    init_db()
    thread = threading.Thread(target=run_fill_loop, daemon=True)
    thread.start()
    compare_thread = threading.Thread(target=run_compare_loop, daemon=True)
    compare_thread.start()
    app.run(host="0.0.0.0", port=port, debug=False)
