import os
import sqlite3
import time


DB_PATH = os.environ.get("DB_PATH", "app.db")
MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "migrations")


def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_migrations_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
        """
    )


def applied_migrations(conn):
    ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {row["version"] for row in rows}


def apply_migration(conn, version, sql):
    conn.executescript(sql)
    conn.execute(
        "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
        (version, int(time.time())),
    )


def run():
    if not os.path.isdir(MIGRATIONS_DIR):
        return
    files = sorted(
        fname for fname in os.listdir(MIGRATIONS_DIR) if fname.endswith(".sql")
    )
    conn = get_db()
    try:
        applied = applied_migrations(conn)
        for fname in files:
            version = os.path.splitext(fname)[0]
            if version in applied:
                continue
            path = os.path.join(MIGRATIONS_DIR, fname)
            with open(path, "r", encoding="utf-8") as handle:
                sql = handle.read()
            apply_migration(conn, version, sql)
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    run()
