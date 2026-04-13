"""
Миграция: переименование ролей в project_permissions.
read → viewer
write → annotator
"""
import sqlite3

def migrate():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Проверяем что таблица существует
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='project_permissions'")
    if not cursor.fetchone():
        print("Таблица project_permissions не найдена — миграция не нужна")
        conn.close()
        return

    # Считаем сколько записей нужно обновить
    cursor.execute("SELECT COUNT(*) FROM project_permissions WHERE role IN ('read', 'write')")
    count = cursor.fetchone()[0]
    print(f"Найдено {count} записей для миграции")

    if count == 0:
        print("Нет записей для миграции")
        conn.close()
        return

    # Миграция
    cursor.execute("UPDATE project_permissions SET role = 'viewer' WHERE role = 'read'")
    read_count = cursor.rowcount

    cursor.execute("UPDATE project_permissions SET role = 'annotator' WHERE role = 'write'")
    write_count = cursor.rowcount

    conn.commit()
    print(f"Мигрировано: read → viewer ({read_count}), write → annotator ({write_count})")

    conn.close()

if __name__ == '__main__':
    migrate()
