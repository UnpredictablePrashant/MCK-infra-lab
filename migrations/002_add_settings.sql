CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

INSERT OR IGNORE INTO settings (key, value, updated_at)
VALUES (
    'baseline_url',
    'http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com/',
    strftime('%s','now')
);
