BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS students (
    url TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS students_new (
    lab TEXT NOT NULL,
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    added_at INTEGER NOT NULL,
    PRIMARY KEY (lab, url)
);

INSERT INTO students_new (lab, url, name, added_at)
SELECT 'lab1', url, name, added_at
FROM students;

DROP TABLE students;
ALTER TABLE students_new RENAME TO students;

CREATE TABLE IF NOT EXISTS leaderboard (
    url TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    last_checked INTEGER,
    sync INTEGER
);

CREATE TABLE IF NOT EXISTS leaderboard_new (
    lab TEXT NOT NULL,
    url TEXT NOT NULL,
    name TEXT NOT NULL,
    last_checked INTEGER,
    sync INTEGER,
    PRIMARY KEY (lab, url)
);

INSERT INTO leaderboard_new (lab, url, name, last_checked, sync)
SELECT 'lab1', url, name, last_checked, sync
FROM leaderboard;

DROP TABLE leaderboard;
ALTER TABLE leaderboard_new RENAME TO leaderboard;

COMMIT;
