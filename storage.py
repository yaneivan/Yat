"""
Storage configuration.

This module defines the base paths and allowed extensions.
For file operations, use ImageStorageService instead.
"""

import os

# --- Конфигурация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')
ORIGINALS_FOLDER = os.path.join(DATA_DIR, 'originals')
PROJECTS_FOLDER = os.path.join(DATA_DIR, 'projects')
THUMBNAILS_FOLDER = os.path.join(DATA_DIR, 'thumbnails')

for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER, ORIGINALS_FOLDER, PROJECTS_FOLDER, THUMBNAILS_FOLDER]:
    os.makedirs(p, exist_ok=True)

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}
