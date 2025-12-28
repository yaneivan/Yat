import os
import shutil
import math
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from PIL import Image, ImageOps # Added ImageOps
import storage

# --- Математика ---

def rotate_point(x, y, cx, cy, angle_deg):
    """
    Вращает точку (x,y) вокруг (cx,cy).
    Угол в градусах.
    """
    rad = math.radians(angle_deg)
    c = math.cos(rad)
    s = math.sin(rad)
    
    nx = cx + (x - cx) * c - (y - cy) * s
    ny = cy + (x - cx) * s + (y - cy) * c
    return nx, ny

def recalculate_regions(regions, old_crop, new_crop):
    """
    Пересчитывает координаты регионов:
    Local (Old) -> Global (Original) -> Local (New)
    """
    if not regions: return []
    
    # 1. Параметры СТАРОГО кропа
    ox = old_crop['x'] if old_crop else 0
    oy = old_crop['y'] if old_crop else 0
    ow = old_crop['w'] if old_crop else 0
    oh = old_crop['h'] if old_crop else 0
    o_angle = old_crop.get('angle', 0) if old_crop else 0
    
    o_cx = ox + ow / 2.0
    o_cy = oy + oh / 2.0

    # 2. Параметры НОВОГО кропа
    nx = new_crop['x']
    ny = new_crop['y']
    nw = new_crop['w']
    nh = new_crop['h']
    n_angle = new_crop.get('angle', 0)
    
    n_cx = nx + nw / 2.0
    n_cy = ny + nh / 2.0

    final_regions = []
    
    for reg in regions:
        new_points = []
        for p in reg['points']:
            # --- Шаг 1: Восстановление на оригинале ---
            p_rot_space_x = p['x'] + ox
            p_rot_space_y = p['y'] + oy
            
            # ИСПРАВЛЕНО: Знак угла. 
            # Кроп делал rotate(-o_angle). Чтобы вернуть, делаем rotate(+o_angle).
            # rotate_point считает + как CCW.
            # Если o_angle=5, Pillow крутил -5 (CW). Нам надо вернуть +5 (CCW).
            # Значит передаем o_angle.
            orig_x, orig_y = rotate_point(p_rot_space_x, p_rot_space_y, o_cx, o_cy, o_angle)
            
            # --- Шаг 2: Применение нового кропа ---
            # Мы хотим координаты внутри картинки, которая будет повернута на -n_angle (CW).
            # Значит точку надо повернуть туда же -> на -n_angle.
            new_rot_x, new_rot_y = rotate_point(orig_x, orig_y, n_cx, n_cy, -n_angle)
            
            # Смещаем
            final_x = new_rot_x - nx
            final_y = new_rot_y - ny
            
            new_points.append({'x': int(round(final_x)), 'y': int(round(final_y))})
            
        final_regions.append({'points': new_points})
            
    return final_regions

# --- Crop ---

def perform_crop(filename, box):
    if not storage.ensure_original_exists(filename):
        return False

    src_path = os.path.join(storage.IMAGE_FOLDER, filename)
    backup_path = os.path.join(storage.ORIGINALS_FOLDER, filename)

    try:
        json_data = storage.load_json(filename)
        old_regions = json_data.get('regions', [])
        old_crop_params = json_data.get('crop_params', None)

        with Image.open(backup_path) as img:
            # ВАЖНО: Учитываем EXIF поворот (телефоны часто сохраняют перевернуто)
            # Иначе координаты браузера и Pillow не совпадут.
            img = ImageOps.exif_transpose(img)
            
            img_w, img_h = img.size
            
            # Clamping
            safe_x = int(round(max(0, min(box['x'], img_w - 1))))
            safe_y = int(round(max(0, min(box['y'], img_h - 1))))
            
            safe_w = int(round(box['w']))
            if safe_x + safe_w > img_w: safe_w = img_w - safe_x
            
            safe_h = int(round(box['h']))
            if safe_y + safe_h > img_h: safe_h = img_h - safe_y
            
            real_box = {
                'x': safe_x, 'y': safe_y, 'w': safe_w, 'h': safe_h, 
                'angle': box.get('angle', 0)
            }

            # Pillow Processing
            cx = real_box['x'] + real_box['w'] / 2.0
            cy = real_box['y'] + real_box['h'] / 2.0
            angle = real_box['angle']
            
            # rotate(-angle) = CW visual rotation
            rotated_img = img.rotate(-angle, center=(cx, cy), resample=Image.BICUBIC, expand=False)
            
            left = real_box['x']
            top = real_box['y']
            right = left + real_box['w']
            bottom = top + real_box['h']
            
            cropped_img = rotated_img.crop((left, top, right, bottom))
            cropped_img.save(src_path)

        # Пересчет
        new_regions = recalculate_regions(old_regions, old_crop_params, real_box)

        # Сохранение
        storage.save_json({
            'image_name': filename,
            'regions': new_regions,
            'crop_params': real_box,
            'status': 'cropped'
        })
            
        return True
    except Exception as e:
        print(f"Crop Error: {e}")
        return False

# --- Helpers (Import/Export) ---

def simplify_points(points, threshold):
    if not points or threshold <= 0: return points
    new_p = [points[0]]
    for p in points[1:]:
        if math.hypot(p['x']-new_p[-1]['x'], p['y']-new_p[-1]['y']) >= threshold:
            new_p.append(p)
    if points[-1] != new_p[-1]: new_p.append(points[-1])
    return new_p

def parse_page_xml(xml_path, simplify_val):
    regions = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {'p': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        prefix = 'p:' if ns else ''
        for line in root.findall(f'.//{prefix}TextLine', ns):
            coords = line.find(f'{prefix}Coords', ns)
            if coords is not None and coords.get('points'):
                pts = []
                for pair in coords.get('points').strip().split():
                    try:
                        x, y = map(float, pair.split(','))
                        pts.append({'x': int(x), 'y': int(y)})
                    except: continue
                if pts:
                    if simplify_val > 0: pts = simplify_points(pts, simplify_val)
                    regions.append({'points': pts})
    except Exception as e: print(f"XML Error: {e}")
    return regions

def process_zip_import(file, simplify_val=0):
    zip_path = os.path.join(storage.TEMP_FOLDER, 'import.zip')
    file.save(zip_path)
    extract_path = os.path.join(storage.TEMP_FOLDER, 'ext')
    if os.path.exists(extract_path): shutil.rmtree(extract_path)
    os.makedirs(extract_path)
    count = 0
    try:
        with zipfile.ZipFile(zip_path, 'r') as z: z.extractall(extract_path)
        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith(tuple(storage.ALLOWED_EXTENSIONS)):
                    src = os.path.join(root, f)
                    storage.save_image(type('obj', (object,), {'filename': f, 'save': lambda p: shutil.move(src, p)}))
                    xml_cands = [os.path.splitext(src)[0]+'.xml', src+'.xml']
                    for xc in xml_cands:
                        if os.path.exists(xc):
                            regs = parse_page_xml(xc, simplify_val)
                            storage.save_json({'image_name': f, 'regions': regs})
                            break
                    count += 1
    finally:
        if os.path.exists(zip_path): os.remove(zip_path)
        if os.path.exists(extract_path): shutil.rmtree(extract_path)
    return count

def generate_export_zip():
    if os.path.exists(storage.EXPORT_FOLDER): shutil.rmtree(storage.EXPORT_FOLDER)
    os.makedirs(storage.EXPORT_FOLDER)
    zname = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    zpath = os.path.join(storage.EXPORT_FOLDER, zname)
    images = storage.get_sorted_images()
    if not images: raise Exception("Нет изображений")
    manifest = []
    with zipfile.ZipFile(zpath, 'w') as zf:
        for idx, img in enumerate(images):
            zf.write(os.path.join(storage.IMAGE_FOLDER, img), arcname=img)
            json_data = storage.load_json(img)
            xml_name = os.path.splitext(img)[0] + '.xml'
            root = ET.Element('PcGts', xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15")
            page = ET.SubElement(root, 'Page', imageFilename=img)
            try:
                with Image.open(os.path.join(storage.IMAGE_FOLDER, img)) as i: w, h = i.size
            except: w, h = 0, 0
            page.set('imageWidth', str(w)); page.set('imageHeight', str(h))
            tr = ET.SubElement(page, 'TextRegion', id='r1')
            for i, reg in enumerate(json_data.get('regions', [])):
                pts = " ".join([f"{p['x']},{p['y']}" for p in reg['points']])
                ln = ET.SubElement(tr, 'TextLine', id=f'l{i}')
                ET.SubElement(ln, 'Coords', points=pts)
            zf.writestr(xml_name, ET.tostring(root, encoding='utf-8'))
            manifest.append({'id': f'f{idx}', 'img': img, 'xml': xml_name})
        mets = ET.Element('mets', xmlns="http://www.loc.gov/METS/")
        fsec = ET.SubElement(mets, 'fileSec')
        fg_img = ET.SubElement(fsec, 'fileGrp', USE='image')
        fg_xml = ET.SubElement(fsec, 'fileGrp', USE='transcription')
        struct = ET.SubElement(mets, 'structMap', TYPE='physical')
        doc = ET.SubElement(struct, 'div', TYPE='document')
        for m in manifest:
            fi = ET.SubElement(fg_img, 'file', ID=m['id']+'i', MIMETYPE='image/jpeg')
            ET.SubElement(fi, 'FLocat', xmlns_xlink="http://www.w3.org/1999/xlink", href=m['img'], LOCTYPE="URL")
            fx = ET.SubElement(fg_xml, 'file', ID=m['id']+'x', MIMETYPE='text/xml')
            ET.SubElement(fx, 'FLocat', xmlns_xlink="http://www.w3.org/1999/xlink", href=m['xml'], LOCTYPE="URL")
            dp = ET.SubElement(doc, 'div', TYPE='page')
            ET.SubElement(dp, 'fptr', FILEID=m['id']+'i')
            ET.SubElement(dp, 'fptr', FILEID=m['id']+'x')
        zf.writestr('METS.xml', ET.tostring(mets, encoding='utf-8'))
    return zpath