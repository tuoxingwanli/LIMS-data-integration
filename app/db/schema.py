"""Idempotent SQLite schema initialization."""

from pathlib import Path

from .connection import connection_scope


def init_db(db_path: Path) -> None:
    """Create current tables without changing existing prototype data."""

    with connection_scope(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS work_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_no TEXT UNIQUE NOT NULL,
                experimenter_id TEXT NOT NULL,
                project_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'in_progress', 'completed', 'pushed')),
                raw_json TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                sample_name TEXT,
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN ('pending', 'completed')),
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
                UNIQUE (work_order_id, sample_no)
            );

            CREATE TABLE IF NOT EXISTS test_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                work_order_id INTEGER NOT NULL,
                sample_no TEXT NOT NULL,
                test_item TEXT NOT NULL,
                value TEXT NOT NULL,
                unit TEXT,
                raw_json TEXT NOT NULL,
                pushed_to_lims INTEGER NOT NULL DEFAULT 0
                    CHECK (pushed_to_lims IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (work_order_id) REFERENCES work_orders(id),
                UNIQUE (work_order_id, sample_no, test_item)
            );

            CREATE TABLE IF NOT EXISTS detection_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blind_sample_no TEXT NOT NULL,
                sample_id INTEGER,
                status TEXT NOT NULL
                    CHECK (status IN ('recording', 'stopped', 'failed')),
                started_at TEXT NOT NULL,
                ended_at TEXT,
                recording_ref TEXT,
                screenshot_ref TEXT,
                capture_mode TEXT NOT NULL,
                error_message TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (sample_id) REFERENCES samples(id)
            );

            CREATE INDEX IF NOT EXISTS idx_work_orders_assignee_status
                ON work_orders(experimenter_id, status, created_at);
            CREATE INDEX IF NOT EXISTS idx_samples_work_order
                ON samples(work_order_id);
            CREATE INDEX IF NOT EXISTS idx_results_work_order
                ON test_results(work_order_id);
            CREATE INDEX IF NOT EXISTS idx_detection_sessions_sample_status
                ON detection_sessions(blind_sample_no, status, started_at);
            """
        )
        connection.commit()
