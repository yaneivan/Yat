import os
import json
import shutil
import zipfile
import math
import xml.etree.ElementTree as ET
from datetime import datetime

# --- Конфигурация путей ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
IMAGE_FOLDER = os.path.join(DATA_DIR, 'images')
ANNOTATION_FOLDER = os.path.join(DATA_DIR, 'annotations')
TEMP_FOLDER = os.path.join(DATA_DIR, 'temp_import')
EXPORT_FOLDER = os.path.join(DATA_DIR, 'temp_export')

# Создаем папки при старте
for p in [IMAGE_FOLDER, ANNOTATION_FOLDER, TEMP_FOLDER, EXPORT_FOLDER]:
    os.makedirs(p, exist_ok=True)

ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}

# --- Базовые операции с файлами ---

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

# --- Алгоритмы ---

def simplify_points(points, threshold):
    """
    Упрощает полигон, удаляя точки, которые ближе threshold (в пикселях) к предыдущей.
    """
    if not points or threshold <= 0:
        return points
    
    new_points = [points[0]]
    for p in points[1:]:
        last = new_points[-1]
        dist = math.hypot(p['x'] - last['x'], p['y'] - last['y'])
        if dist >= threshold:
            new_points.append(p)
    
    # Всегда добавляем последнюю точку, если она не совпадает с последней добавленной
    if points[-1] != new_points[-1]:
        new_points.append(points[-1])
        
    return new_points

# --- Логика Импорта (eScriptorium ZIP) ---

def parse_page_xml_coords(xml_path, simplify_threshold=0):
    regions = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {}
        # Определяем namespace, если он есть
        if '}' in root.tag:
            ns_url = root.tag.split('}')[0].strip('{')
            ns = {'p': ns_url}
        
        prefix = 'p:' if ns else ''
        # Ищем TextLine
        lines = root.findall(f'.//{prefix}TextLine', ns)
        
        for line in lines:
            coords_elem = line.find(f'{prefix}Coords', ns)
            if coords_elem is not None:
                points_str = coords_elem.get('points')
                if points_str:
                    points = []
                    # Формат обычно "x,y x,y x,y"
                    for pair in points_str.strip().split():
                        try:
                            parts = pair.split(',')
                            x = float(parts[0])
                            y = float(parts[1])
                            points.append({'x': int(x), 'y': int(y)})
                        except ValueError: continue
                    
                    if points:
                        # Упрощение
                        if simplify_threshold > 0:
                            points = simplify_points(points, simplify_threshold)
                        regions.append({'points': points})
    except Exception as e:
        print(f"XML Parse Error ({xml_path}): {e}")
    return regions

def process_zip_import(file_storage, simplify_val=0):
    zip_path = os.path.join(TEMP_FOLDER, 'import.zip')
    file_storage.save(zip_path)
    
    extract_path = os.path.join(TEMP_FOLDER, 'extracted')
    if os.path.exists(extract_path): shutil.rmtree(extract_path)
    os.makedirs(extract_path)
    
    count = 0
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_path)
            
        all_files = []
        for root, _, files in os.walk(extract_path):
            for f in files:
                all_files.append(os.path.join(root, f))
                
        # Ищем картинки
        images = [f for f in all_files if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        
        for src_img_path in images:
            filename = os.path.basename(src_img_path)
            # Перемещаем картинку в рабочую папку
            shutil.move(src_img_path, os.path.join(IMAGE_FOLDER, filename))
            
            # Пытаемся найти XML с таким же именем
            base_no_ext = os.path.splitext(src_img_path)[0]
            xml_candidates = [base_no_ext + '.xml', src_img_path + '.xml']
            
            found_xml = None
            for xc in xml_candidates:
                if os.path.exists(xc):
                    found_xml = xc
                    break
            
            if found_xml:
                regions = parse_page_xml_coords(found_xml, simplify_threshold=simplify_val)
                # Сохраняем JSON
                save_annotation({'image_name': filename, 'regions': regions})
            
            count += 1
            
    except Exception as e:
        print(f"Import Error: {e}")
        return 0
    finally:
        # Чистка мусора
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists(extract_path): shutil.rmtree(extract_path)
        
    return count

# --- Логика Экспорта (PageXML + METS ZIP) ---
def create_export_zip():
    if os.path.exists(EXPORT_FOLDER): shutil.rmtree(EXPORT_FOLDER)
    os.makedirs(EXPORT_FOLDER)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"export_{timestamp}.zip"
    zip_path = os.path.join(EXPORT_FOLDER, zip_filename)

    images = [f for f in os.listdir(IMAGE_FOLDER) if f.lower().endswith(tuple(ALLOWED_EXTENSIONS))]
    images.sort()

    # ИСПРАВЛЕНИЕ: Проверка на пустой проект
    if not images:
        raise Exception("Проект пуст! Нет изображений для экспорта.")

    files_manifest = []

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for idx, img_name in enumerate(images):
            img_path = os.path.join(IMAGE_FOLDER, img_name)
            zipf.write(img_path, arcname=img_name)
            
            width, height = 0, 0
            try:
                from PIL import Image
                with Image.open(img_path) as pil_img:
                    width, height = pil_img.size
            except ImportError:
                pass 

            json_name = os.path.splitext(img_name)[0] + '.json'
            json_path = os.path.join(ANNOTATION_FOLDER, json_name)
            xml_name = os.path.splitext(img_name)[0] + '.xml'
            
            has_xml = False
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                xml_str = generate_page_xml(img_name, width, height, data.get('regions', []))
                zipf.writestr(xml_name, xml_str)
                has_xml = True
            
            files_manifest.append({
                'id': f"file_{idx}",
                'img': img_name,
                'xml': xml_name if has_xml else None
            })

        mets_str = generate_mets(files_manifest)
        zipf.writestr("METS.xml", mets_str)

    return zip_path

def generate_page_xml(filename, width, height, regions):
    """Создает контент PageXML файла"""
    NS = 'http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15'
    ET.register_namespace('', NS)
    
    root = ET.Element(f'{{{NS}}}PcGts')
    meta = ET.SubElement(root, f'{{{NS}}}Metadata')
    ET.SubElement(meta, f'{{{NS}}}Creator').text = "HTR Polygon Tool"
    ET.SubElement(meta, f'{{{NS}}}Created').text = datetime.now().isoformat()
    
    page = ET.SubElement(root, f'{{{NS}}}Page', {
        'imageFilename': filename,
        'imageWidth': str(width),
        'imageHeight': str(height)
    })
    
    # Один общий TextRegion
    text_region = ET.SubElement(page, f'{{{NS}}}TextRegion', {'id': 'region_main'})
    # Координаты региона (весь лист)
    ET.SubElement(text_region, f'{{{NS}}}Coords', {
        'points': f"0,0 {width},0 {width},{height} 0,{height}"
    })

    for i, reg in enumerate(regions):
        points_list = reg.get('points', [])
        if not points_list: continue
        
        # Формируем строку точек "x,y x,y ..."
        points_str = " ".join([f"{p['x']},{p['y']}" for p in points_list])
        
        line = ET.SubElement(text_region, f'{{{NS}}}TextLine', {'id': f'line_{i}'})
        ET.SubElement(line, f'{{{NS}}}Coords', {'points': points_str})
        
        # Baseline (создадим фиктивный, если нет данных, просто копия coords для совместимости)
        # В реальном escriptorium baseline - это отдельная линия. 
        # Здесь опустим, чтобы не усложнять, валидаторы обычно пропускают без него или с пустым.

    return ET.tostring(root, encoding='utf-8', method='xml')

def generate_mets(manifest):
    """Создает контент METS файла"""
    NS = "http://www.loc.gov/METS/"
    XLINK = "http://www.w3.org/1999/xlink"
    ET.register_namespace('', NS)
    ET.register_namespace('xlink', XLINK)
    
    root = ET.Element(f'{{{NS}}}mets')
    
    # Секция файлов
    fileSec = ET.SubElement(root, f'{{{NS}}}fileSec')
    fileGrpImg = ET.SubElement(fileSec, f'{{{NS}}}fileGrp', {'USE': 'image'})
    fileGrpXml = ET.SubElement(fileSec, f'{{{NS}}}fileGrp', {'USE': 'transcription'})
    
    # Карта структуры
    structMap = ET.SubElement(root, f'{{{NS}}}structMap', {'TYPE': 'physical'})
    divDoc = ET.SubElement(structMap, f'{{{NS}}}div', {'TYPE': 'document'})

    for item in manifest:
        fid = item['id']
        
        # Image
        f_img = ET.SubElement(fileGrpImg, f'{{{NS}}}file', {'ID': f"{fid}_img", 'MIMETYPE': 'image/jpeg'})
        ET.SubElement(f_img, f'{{{NS}}}FLocat', {
            'LOCTYPE': 'URL', 
            f'{{{XLINK}}}href': item['img']
        })
        
        # XML
        if item['xml']:
            f_xml = ET.SubElement(fileGrpXml, f'{{{NS}}}file', {'ID': f"{fid}_xml", 'MIMETYPE': 'text/xml'})
            ET.SubElement(f_xml, f'{{{NS}}}FLocat', {
                'LOCTYPE': 'URL', 
                f'{{{XLINK}}}href': item['xml']
            })

        # Связь в структуре
        divPage = ET.SubElement(divDoc, f'{{{NS}}}div', {'TYPE': 'page'})
        ET.SubElement(divPage, f'{{{NS}}}fptr', {'FILEID': f"{fid}_img"})
        if item['xml']:
            ET.SubElement(divPage, f'{{{NS}}}fptr', {'FILEID': f"{fid}_xml"})

    return ET.tostring(root, encoding='utf-8', method='xml')