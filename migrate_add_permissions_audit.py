"""Миграция: таблицы project_permissions и audit_log."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # ── project_permissions ──
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_permissions'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE project_permissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                role VARCHAR(20) NOT NULL DEFAULT 'write',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX ix_perm_user ON project_permissions(user_id)")
        cursor.execute("CREATE INDEX ix_perm_project ON project_permissions(project_id)")
        cursor.execute("CREATE UNIQUE INDEX ix_perm_unique ON project_permissions(user_id, project_id)")
        print("Таблица 'project_permissions' создана.")
    else:
        print("Таблица 'project_permissions' уже существует.")

    # ── audit_log ──
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'")
    if not cursor.fetchone():
        cursor.execute("""
            CREATE TABLE audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action VARCHAR(50) NOT NULL,
                entity_type VARCHAR(50) NOT NULL,
                entity_id INTEGER,
                old_value TEXT,
                new_value TEXT,
                details TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
        """)
        cursor.execute("CREATE INDEX ix_audit_user ON audit_log(user_id)")
        cursor.execute("CREATE INDEX ix_audit_action ON audit_log(action)")
        cursor.execute("CREATE INDEX ix_audit_entity ON audit_log(entity_type, entity_id)")
        cursor.execute("CREATE INDEX ix_audit_time ON audit_log(created_at)")
        print("Таблица 'audit_log' создана.")
    else:
        print("Таблица 'audit_log' уже существует.")

    conn.commit()
    conn.close()
    print("Миграция завершена.")


if __name__ == '__main__':
    migrate()
