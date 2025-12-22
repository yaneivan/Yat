import os
import json
import shutil
import zipfile
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}

# Инициализация папок
for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER]:
    os.makedirs(p, exist_ok=True)

def get_sorted_images():
    files = [f for f in os.listdir(IMAGE_FOLDER) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
    files.sort()
    return files

def save_image(file_storage):
    if file_storage and file_storage.filename:
        path = os.path.join(IMAGE_FOLDER, file_storage.filename)
        file_storage.save(path)
        return True
    return False

def delete_files(filenames):
    deleted = 0
    for fname in filenames:
        # Картинка
        img_path = os.path.join(IMAGE_FOLDER, fname)
        if os.path.exists(img_path):
            os.remove(img_path)
            deleted += 1
        # JSON
        json_name = os.path.splitext(fname)[0] + '.json'
        json_path = os.path.join(ANNOTATION_FOLDER, json_name)
        if os.path.exists(json_path):
            os.remove(json_path)
    return deleted

def load_annotation(filename):
    json_name = os.path.splitext(filename)[0] + '.json'
    path = os.path.join(ANNOTATION_FOLDER, json_name)
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'regions': []}

def save_annotation(data):
    image_name = data.get('image_name')
    if not image_name: return False
    
    json_name = os.path.splitext(image_name)[0] + '.json'
    path = os.path.join(ANNOTATION_FOLDER, json_name)
    
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)
    return True

# --- Логика Импорта (eScriptorium) ---

def parse_page_xml_coords(xml_path):
    regions = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {}
        if '}' in root.tag:
            ns_url = root.tag.split('}')[0].strip('{')
            ns = {'p': ns_url}
        
        prefix = 'p:' if ns else ''
        lines = root.findall(f'.//{prefix}TextLine', ns)
        
        for line in lines:
            coords_elem = line.find(f'{prefix}Coords', ns)
            if coords_elem is not None:
                points_str = coords_elem.get('points')
                if points_str:
                    points = []
                    for pair in points_str.strip().split():
                        try:
                            x, y = map(int, map(float, pair.split(','))) # float safe
                            points.append({'x': int(x), 'y': int(y)})
                        except ValueError: continue
                    if points: regions.append({'points': points})
    except Exception as e:
        print(f"XML Error: {e}")
    return regions

def process_zip_import(file_storage):
    zip_path = os.path.join(TEMP_FOLDER, 'import.zip')
    file_storage.save(zip_path)
    
    extract_path = os.path.join(TEMP_FOLDER, 'extracted')
    if os.path.exists(extract_path): shutil.rmtree(extract_path)
    os.makedirs(extract_path)
    
    count = 0
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_path)
            
        # Упрощенная логика: ищем пары (img, xml) по имени
        # (Полная логика с METS тоже возможна, но для краткости оставим fallback, он надежнее)
        all_files = []
        for root, _, files in os.walk(extract_path):
            for f in files:
                all_files.append(os.path.join(root, f))
                
        images = [f for f in all_files if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        
        for src_img_path in images:
            filename = os.path.basename(src_img_path)
            # Перемещаем картинку
            shutil.move(src_img_path, os.path.join(IMAGE_FOLDER, filename))
            
            # Ищем XML рядом
            base_no_ext = os.path.splitext(src_img_path)[0]
            xml_candidates = [base_no_ext + '.xml', src_img_path + '.xml']
            
            found_xml = None
            for xc in xml_candidates:
                if os.path.exists(xc):
                    found_xml = xc
                    break
            
            if found_xml:
                regions = parse_page_xml_coords(found_xml)
                save_annotation({'image_name': filename, 'regions': regions})
            
            count += 1
            
    except Exception as e:
        print(f"Import Error: {e}")
        return 0
    finally:
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists(extract_path): shutil.rmtree(extract_path)
        
    return count