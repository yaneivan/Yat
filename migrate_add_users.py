"""Миграция: добавление таблицы users для системы аутентификации."""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'database.db')


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Проверка существует ли таблица
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if cursor.fetchone():
        print("Таблица 'users' уже существует, миграция не требуется.")
        conn.close()
        return

    # Создание таблицы users
    cursor.execute("""
        CREATE TABLE users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(256) NOT NULL,
            role VARCHAR(20) NOT NULL DEFAULT 'annotator',
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Индексы
    cursor.execute("CREATE INDEX ix_users_username ON users(username)")

    conn.commit()
    conn.close()
    print("Миграция завершена: таблица 'users' создана.")


if __name__ == '__main__':
    migrate()
