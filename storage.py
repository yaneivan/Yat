import os
import json
import shutil

# --- Конфигурация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')
EXPORT_FOLDER = os.path.join(DATA_DIR, 'temp_export')
ORIGINALS_FOLDER = os.path.join(DATA_DIR, 'originals')

for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER, EXPORT_FOLDER, ORIGINALS_FOLDER]:
    os.makedirs(p, exist_ok=True)

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}

def get_sorted_images():
    files = [f for f in os.listdir(IMAGE_FOLDER) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
    files.sort()
    return files

def get_images_with_status():
    files = get_sorted_images()
    result = []
    for f in files:
        json_path = os.path.join(ANNOTATION_FOLDER, os.path.splitext(f)[0] + '.json')
        # Читаем JSON, чтобы узнать, был ли файл уже обрезан (есть ли crop_params)
        status = 'crop'
        if os.path.exists(json_path):
            try:
                with open(json_path, 'r') as jf:
                    data = json.load(jf)
                    # Если есть регионы или явный статус - готово к сегментации
                    if data.get('regions') or data.get('status') == 'cropped':
                        status = 'segment'
            except: pass
        
        result.append({'name': f, 'status': status})
    return result

def save_image(file_storage):
    if file_storage and file_storage.filename:
        path = os.path.join(IMAGE_FOLDER, file_storage.filename)
        file_storage.save(path)
        # Сразу делаем копию в оригиналы, чтобы всегда был исходник
        shutil.copy(path, os.path.join(ORIGINALS_FOLDER, file_storage.filename))
        return True
    return False

def delete_file_set(filenames):
    deleted = 0
    for fname in filenames:
        p1 = os.path.join(IMAGE_FOLDER, fname)
        if os.path.exists(p1): os.remove(p1); deleted += 1
        p2 = os.path.join(ANNOTATION_FOLDER, os.path.splitext(fname)[0] + '.json')
        if os.path.exists(p2): os.remove(p2)
        p3 = os.path.join(ORIGINALS_FOLDER, fname)
        if os.path.exists(p3): os.remove(p3)
    return deleted

def load_json(filename):
    name = os.path.splitext(filename)[0] + '.json'
    path = os.path.join(ANNOTATION_FOLDER, name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'regions': [], 'crop_params': None}

def save_json(data):
    image_name = data.get('image_name')
    if not image_name: return False
    name = os.path.splitext(image_name)[0] + '.json'
    path = os.path.join(ANNOTATION_FOLDER, name)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return True

def ensure_original_exists(filename):
    """Проверяет, есть ли файл в originals. Если нет - копирует из images."""
    src = os.path.join(IMAGE_FOLDER, filename)
    dst = os.path.join(ORIGINALS_FOLDER, filename)
    if not os.path.exists(dst) and os.path.exists(src):
        shutil.copy(src, dst)
    return os.path.exists(dst)