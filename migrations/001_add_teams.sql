CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lab TEXT NOT NULL,
    name TEXT NOT NULL,
    members TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    UNIQUE(lab, name)
);

INSERT OR IGNORE INTO teams (lab, name, members, created_at, updated_at)
VALUES
    ('lab1', 'Team 1', 'Dev, Ravish, Shobhit, Me', strftime('%s','now'), strftime('%s','now')),
    ('lab1', 'Team 2', 'Akash, Vinita, Mayank, Kashish', strftime('%s','now'), strftime('%s','now')),
    ('lab1', 'Team 3', 'Paulo, Gary, Jimmy, Harinath', strftime('%s','now'), strftime('%s','now')),
    ('lab1', 'Team 4', 'Sudhanshu, Nikhil, Amit', strftime('%s','now'), strftime('%s','now'));
