import os
import json
import shutil
from datetime import datetime
import re

# --- Конфигурация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')
EXPORT_FOLDER = os.path.join(DATA_DIR, 'temp_export')
ORIGINALS_FOLDER = os.path.join(DATA_DIR, 'originals')
PROJECTS_FOLDER = os.path.join(DATA_DIR, 'projects')

for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER, EXPORT_FOLDER, ORIGINALS_FOLDER, PROJECTS_FOLDER]:
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
            data = json.load(f)
            # Ensure texts field exists
            if 'texts' not in data:
                data['texts'] = {}
            return data
    return {'regions': [], 'texts': {}, 'crop_params': None}

def save_json(data):
    image_name = data.get('image_name')
    if not image_name: return False
    name = os.path.splitext(image_name)[0] + '.json'
    path = os.path.join(ANNOTATION_FOLDER, name)
    # Ensure texts field exists before saving
    if 'texts' not in data:
        data['texts'] = {}
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


# --- Project Management Functions ---
def create_project(project_name, description=""):
    """Create a new project with the given name and description"""
    # Validate project name
    if not project_name or not project_name.strip():
        return False, "Project name cannot be empty"

    # Sanitize project name to be a valid directory name
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
    if not sanitized_name:
        return False, "Invalid project name"

    # Create project directory
    project_dir = os.path.join(PROJECTS_FOLDER, sanitized_name)
    if os.path.exists(project_dir):
        return False, "Project already exists"

    try:
        os.makedirs(project_dir, exist_ok=True)

        # Create project metadata - keep original name in the data
        project_data = {
            'name': project_name,  # Keep original name in the data
            'description': description,
            'created_at': datetime.now().isoformat(),
            'images': []
        }

        project_json_path = os.path.join(project_dir, 'project.json')
        with open(project_json_path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4, ensure_ascii=False)

        return True, project_data
    except Exception as e:
        return False, f"Error creating project: {str(e)}"


def get_projects_list():
    """Get a list of all projects"""
    projects = []
    for project_dir_name in os.listdir(PROJECTS_FOLDER):
        project_path = os.path.join(PROJECTS_FOLDER, project_dir_name)
        if os.path.isdir(project_path):
            project_json_path = os.path.join(project_path, 'project.json')
            if os.path.exists(project_json_path):
                with open(project_json_path, 'r', encoding='utf-8') as f:
                    project_data = json.load(f)
                    projects.append(project_data)
    return projects


def get_project_images(project_name):
    """Get a list of images in a project"""
    # Sanitize project name to match directory name
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
    project_path = os.path.join(PROJECTS_FOLDER, sanitized_name)
    project_json_path = os.path.join(project_path, 'project.json')

    if not os.path.exists(project_json_path):
        return []

    with open(project_json_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)
        return project_data.get('images', [])


def add_image_to_project(project_name, image_name):
    """Add an image to a project"""
    # Sanitize project name to match directory name
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
    project_path = os.path.join(PROJECTS_FOLDER, sanitized_name)
    project_json_path = os.path.join(project_path, 'project.json')

    if not os.path.exists(project_json_path):
        return False, "Project does not exist"

    with open(project_json_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Check if image is already in the project
    if image_name in project_data['images']:
        return False, "Image already in project"

    # Add image to project
    project_data['images'].append(image_name)

    with open(project_json_path, 'w', encoding='utf-8') as f:
        json.dump(project_data, f, indent=4, ensure_ascii=False)

    return True, project_data


def remove_image_from_project(project_name, image_name):
    """Remove an image from a project"""
    # Sanitize project name to match directory name
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
    project_path = os.path.join(PROJECTS_FOLDER, sanitized_name)
    project_json_path = os.path.join(project_path, 'project.json')

    if not os.path.exists(project_json_path):
        return False, "Project does not exist"

    with open(project_json_path, 'r', encoding='utf-8') as f:
        project_data = json.load(f)

    # Remove image from project
    if image_name in project_data['images']:
        project_data['images'].remove(image_name)

        with open(project_json_path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4, ensure_ascii=False)

        return True, project_data

    return False, "Image not in project"


def delete_project(project_name):
    """Delete a project and its metadata"""
    # Sanitize project name to match directory name
    sanitized_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
    project_path = os.path.join(PROJECTS_FOLDER, sanitized_name)

    if not os.path.exists(project_path):
        return False, "Project does not exist"

    # Remove the entire project directory
    shutil.rmtree(project_path)
    return True, "Project deleted successfully"


def get_project_status(project_name):
    """Get the status of a project based on its images"""
    images = get_project_images(project_name)
    if not images:
        return 'empty'

    # Count how many images have annotations
    annotated_count = 0
    for image_name in images:
        json_path = os.path.join(ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')
        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if data.get('regions') or data.get('status') == 'cropped':
                    annotated_count += 1

    if annotated_count == 0:
        return 'crop'
    elif annotated_count == len(images):
        return 'segment'
    else:
        return 'partial'