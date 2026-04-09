"""
Миграция: генерация миниатюр для всех существующих изображений.

Запуск:
    uv run python migrate_thumbnails.py
"""

import os

from storage import IMAGE_FOLDER, THUMBNAILS_FOLDER, ALLOWED_EXTENSIONS
from services.image_storage_service import image_storage_service


def generate_all_thumbnails(max_size=300):
    """Generate thumbnails for all existing images."""
    total = 0
    success = 0
    failed = 0

    # Сканируем data/images/ рекурсивно (включая подпапки проектов)
    for root, dirs, files in os.walk(IMAGE_FOLDER):
        for filename in files:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in ALLOWED_EXTENSIONS:
                continue

            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, IMAGE_FOLDER)

            # Определить проект (если файл в подпапке)
            parts = rel_path.split(os.sep)
            project_name = parts[0] if len(parts) > 1 else None

            total += 1
            print(f"[{total}] {rel_path}...", end=" ")

            # Проверить есть ли уже миниатюра
            if image_storage_service.thumbnail_exists(filename, project_name):
                print("уже есть")
                success += 1
                continue

            result = image_storage_service.generate_thumbnail(filename, project_name, max_size)
            if result:
                print("OK")
                success += 1
            else:
                print("ОШИБКА")
                failed += 1

    print(f"\n=== Итого: {total}, успешно: {success}, ошибок: {failed} ===")

    # Посчитать размер
    thumb_size = 0
    for root, dirs, files in os.walk(THUMBNAILS_FOLDER):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.exists(fp):
                thumb_size += os.path.getsize(fp)

    img_size = 0
    for root, dirs, files in os.walk(IMAGE_FOLDER):
        for f in files:
            fp = os.path.join(root, f)
            if os.path.exists(fp):
                img_size += os.path.getsize(fp)

    print(f"Размер оригиналов: {img_size / 1024 / 1024:.1f} MB")
    print(f"Размер миниатюр:   {thumb_size / 1024 / 1024:.1f} MB")
    if img_size > 0:
        print(f"Экономия:          {(1 - thumb_size / img_size) * 100:.0f}%")


if __name__ == '__main__':
    generate_all_thumbnails()
