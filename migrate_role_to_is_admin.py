"""Миграция: замена колонки role на is_admin в таблице users."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверка существует ли колонка is_admin
    cursor.execute("PRAGMA table_info(users)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'is_admin' in columns and 'role' not in columns:
        print("Миграция уже применена.")
        conn.close()
        return

    # Создаём новую таблицу
    cursor.execute("""
        CREATE TABLE users_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Копируем данные: role='admin' → is_admin=1, остальные → 0
    cursor.execute("""
        INSERT INTO users_new (id, username, password_hash, is_admin, created_at, updated_at)
        SELECT 
            id, 
            username, 
            password_hash, 
            CASE WHEN role = 'admin' THEN 1 ELSE 0 END,
            created_at, 
            updated_at 
        FROM users
    """)

    cursor.execute("DROP TABLE users")
    cursor.execute("ALTER TABLE users_new RENAME TO users")
    cursor.execute("CREATE INDEX ix_users_username ON users(username)")

    conn.commit()
    conn.close()
    print("Миграция завершена: role → is_admin")


if __name__ == '__main__':
    migrate()
