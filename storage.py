import os

# --- Конфигурация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')
ORIGINALS_FOLDER = os.path.join(DATA_DIR, 'originals')
PROJECTS_FOLDER = os.path.join(DATA_DIR, 'projects')

for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER, ORIGINALS_FOLDER, PROJECTS_FOLDER]:
    os.makedirs(p, exist_ok=True)

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}


def get_sorted_images():
    """Get sorted list of image files."""
    files = [f for f in os.listdir(IMAGE_FOLDER) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
    files.sort()
    return files


def get_images_with_status():
    """Get all images with their status using annotation_service"""
    from services.annotation_service import annotation_service

    files = get_sorted_images()
    result = []
    for f in files:
        status = annotation_service.get_status(f)
        result.append({'name': f, 'status': status})
    return result
