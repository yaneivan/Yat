"""Миграция: удаление колонки is_active из таблицы users."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверка существует ли колонка
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'is_active' not in columns:
        print("Колонка 'is_active' уже удалена, миграция не требуется.")
        conn.close()
        return

    # SQLite не поддерживает DROP COLUMN до версии 3.35.0
    # Пересоздаём таблицу без колонки
    cursor.execute("""
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'annotator',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        INSERT INTO users_new (id, username, password_hash, role, created_at, updated_at)
        SELECT id, username, password_hash, role, created_at, updated_at FROM users
    """)

    cursor.execute("DROP TABLE users")
    cursor.execute("ALTER TABLE users_new RENAME TO users")
    cursor.execute("CREATE INDEX ix_users_username ON users(username)")

    conn.commit()
    conn.close()
    print("Миграция завершена: колонка 'is_active' удалена.")


if __name__ == '__main__':
    migrate()
