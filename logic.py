import os
import shutil
import math
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from PIL import Image, ImageOps # Added ImageOps
import storage
import json

# YOLOv9 imports
try:
    import torch
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False
    print("YOLOv9 not available. Install ultralytics and torch to enable text-line detection.")

# TROCR imports
try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False
    print("Transformers not available. Install transformers to enable text recognition.")

# Global variables to store TROCR model and processor
trocr_model = None
trocr_processor = None

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

def calculate_polygon_area(points):
    """
    Calculate the area of a polygon using the Shoelace formula.
    """
    if len(points) < 3:
        return 0

    area = 0
    n = len(points)

    for i in range(n):
        j = (i + 1) % n
        area += points[i]['x'] * points[j]['y']
        area -= points[j]['x'] * points[i]['y']

    return abs(area) / 2

def merge_overlapping_regions(regions, overlap_threshold=30):
    """
    Merge overlapping regions in the list based on overlap threshold.
    overlap_threshold: percentage of area overlap required to merge regions
    """
    print(f"Starting merge process with {len(regions)} regions and overlap_threshold {overlap_threshold}%")  # Отладочный вывод

    if not regions:
        return regions

    # Create a working copy of regions
    unprocessed_regions = [r.copy() for r in regions]
    merged_regions = []

    # Process each region once
    while unprocessed_regions:
        current_region = unprocessed_regions.pop(0)
        print(f"Processing region with {len(current_region['points'])} points")  # Отладочный вывод

        # Find all regions that can be merged with current_region
        regions_to_merge = []
        for other_region in unprocessed_regions[:]:  # Create a copy to iterate
            overlap_ratio = calculate_overlap_ratio(current_region['points'], other_region['points'])
            is_spatially_close = are_regions_spatially_close(current_region['points'], other_region['points'])

            print(f"  Comparing with other region: overlap_ratio={overlap_ratio:.2f}%, is_spatially_close={is_spatially_close}, threshold={overlap_threshold}%")  # Отладочный вывод

            if overlap_ratio >= overlap_threshold and is_spatially_close:
                print(f"    Marking for merging")  # Отладочный вывод
                regions_to_merge.append(other_region)

        # Merge all marked regions with current region
        final_region = current_region
        for region_to_merge in regions_to_merge:
            print(f"  Merging region")  # Отладочный вывод
            final_region = merge_two_polygons(final_region['points'], region_to_merge['points'])
            unprocessed_regions.remove(region_to_merge)  # Remove from unprocessed list

        merged_regions.append(final_region)
        print(f"  Added merged region to results")  # Отладочный вывод

    print(f"Merge process complete: {len(regions)} -> {len(merged_regions)} regions")  # Отладочный вывод
    return merged_regions

def are_regions_spatially_close(points1, points2):
    """
    Check if two regions are spatially close to each other.
    This prevents merging distant regions that happen to have some overlap due to bounding box approximation.
    """
    # Calculate centroids of both regions
    centroid1_x = sum(p['x'] for p in points1) / len(points1)
    centroid1_y = sum(p['y'] for p in points1) / len(points1)

    centroid2_x = sum(p['x'] for p in points2) / len(points2)
    centroid2_y = sum(p['y'] for p in points2) / len(points2)

    # Calculate distance between centroids
    distance = math.sqrt((centroid1_x - centroid2_x)**2 + (centroid1_y - centroid2_y)**2)

    # Calculate average size of regions (using bounding box dimensions)
    width1 = max(p['x'] for p in points1) - min(p['x'] for p in points1)
    height1 = max(p['y'] for p in points1) - min(p['y'] for p in points1)
    size1 = math.sqrt(width1 * height1)  # Geometric mean as size approximation

    width2 = max(p['x'] for p in points2) - min(p['x'] for p in points2)
    height2 = max(p['y'] for p in points2) - min(p['y'] for p in points2)
    size2 = math.sqrt(width2 * height2)  # Geometric mean as size approximation

    avg_size = (size1 + size2) / 2

    # Regions are considered close if distance between centroids is less than 3x average size
    # Using a more generous threshold to allow for reasonable merging
    return distance < avg_size * 3

def calculate_overlap_ratio(points1, points2):
    """
    Calculate the overlap ratio between two polygons as a percentage of the smaller polygon.
    This is a simplified implementation using bounding box approximation.
    """
    # Get bounding boxes
    min_x1 = min(p['x'] for p in points1)
    max_x1 = max(p['x'] for p in points1)
    min_y1 = min(p['y'] for p in points1)
    max_y1 = max(p['y'] for p in points1)

    min_x2 = min(p['x'] for p in points2)
    max_x2 = max(p['x'] for p in points2)
    min_y2 = min(p['y'] for p in points2)
    max_y2 = max(p['y'] for p in points2)

    # Calculate intersection area
    inter_x1 = max(min_x1, min_x2)
    inter_y1 = max(min_y1, min_y2)
    inter_x2 = min(max_x1, max_x2)
    inter_y2 = min(max_y1, max_y2)

    if inter_x1 < inter_x2 and inter_y1 < inter_y2:
        intersection_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)

        area1 = calculate_polygon_area(points1)
        area2 = calculate_polygon_area(points2)

        # Calculate the overlap as percentage of the intersection relative to the union
        union_area = area1 + area2 - intersection_area
        if union_area > 0:
            # Jaccard similarity (intersection over union)
            jaccard_similarity = (intersection_area / union_area) * 100
            return jaccard_similarity
        else:
            return 0
    else:
        return 0

def polygons_overlap(points1, points2):
    """
    Check if two polygons overlap using bounding box check as a simple approximation.
    """
    # Get bounding boxes
    min_x1 = min(p['x'] for p in points1)
    max_x1 = max(p['x'] for p in points1)
    min_y1 = min(p['y'] for p in points1)
    max_y1 = max(p['y'] for p in points1)

    min_x2 = min(p['x'] for p in points2)
    max_x2 = max(p['x'] for p in points2)
    min_y2 = min(p['y'] for p in points2)
    max_y2 = max(p['y'] for p in points2)

    # Check if bounding boxes overlap
    return not (max_x1 < min_x2 or max_x2 < min_x1 or max_y1 < min_y2 or max_y2 < min_y1)

def merge_two_polygons(points1, points2):
    """
    Merge two polygons by combining them into a single polygon.
    This creates a more natural union of the two polygons by using a
    simplified approach that maintains the general shape.
    """
    import math

    # For a more natural merge, we'll create a polygon that connects
    # the two polygons through their closest points
    all_points = points1 + points2

    # Use convex hull as a simple approach, but we could implement
    # a more sophisticated polygon union algorithm if needed
    hull_points = convex_hull(all_points)

    return {'points': hull_points}

def convex_hull(points):
    """
    Find the convex hull of a set of points using Graham scan algorithm.
    """
    def polar_angle(p0, p1):
        if p0['x'] == p1['x']:
            return float('inf')
        return math.atan2(p1['y'] - p0['y'], p1['x'] - p0['x'])

    def distance_squared(p0, p1):
        return (p1['x'] - p0['x']) ** 2 + (p1['y'] - p0['y']) ** 2

    def cross_product(o, a, b):
        return (a['x'] - o['x']) * (b['y'] - o['y']) - (a['y'] - o['y']) * (b['x'] - o['x'])

    # Find the bottom-most point (or left most in case of tie)
    start = min(points, key=lambda p: (p['y'], p['x']))

    # Sort points by polar angle with respect to start
    sorted_points = sorted(points, key=lambda p: (polar_angle(start, p), distance_squared(start, p)))

    # Create and return convex hull
    hull = []
    for point in sorted_points:
        while len(hull) > 1 and cross_product(hull[-2], hull[-1], point) <= 0:
            hull.pop()
        hull.append(point)

    return hull

def detect_text_lines_yolo(filename, settings=None):
    """
    Detect text lines in an image using YOLOv9 model.
    Returns a list of regions (polygons) representing detected text lines.
    """
    if settings is None:
        settings = {}

    if not YOLO_AVAILABLE:
        raise Exception("YOLOv9 not available. Install ultralytics and torch to enable text-line detection.")

    # Load the YOLOv9 instance segmentation model for text-line detection
    # Based on the model you specified: yolov9-lines-within-regions-handwritten
    # This model is designed for segmenting text-lines within text-regions
    # First check in models folder, then in root directory (following README recommendations)
    model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models', 'model.pt')

    if not os.path.exists(model_path):
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'model.pt')

    # Check if model file exists
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"YOLOv9 model not found at {model_path}. Please ensure the model file is in the project root or models directory.")

    # Load the specific model for text-line detection within regions
    model = YOLO(model_path)

    # Get the image path
    image_path = os.path.join(storage.IMAGE_FOLDER, filename)
    if not os.path.exists(image_path):
        raise Exception(f"Image file does not exist: {image_path}")

    # Get detection parameters from settings
    confidence_threshold = settings.get('threshold', 50) / 100.0  # Convert percentage to decimal

    # Run inference with confidence threshold
    results = model(image_path, conf=confidence_threshold)

    # Get additional settings
    simplification_threshold = settings.get('simplification', 2.0)
    merge_overlapping = settings.get('mergeOverlapping', False)
    overlap_threshold = settings.get('overlapThreshold', 30)  # Percentage of overlap required to merge

    print(f"Using settings - simplification: {simplification_threshold}, merge_overlapping: {merge_overlapping}, overlap_threshold: {overlap_threshold}")  # Отладочный вывод

    # Process results - we want segmentation masks for text lines
    regions = []
    for result in results:
        if result.masks is not None:
            # Process segmentation masks (this is what we want for text-line segmentation)
            masks = result.masks.xy  # List of masks as numpy arrays
            for mask in masks:
                # Convert mask to the format expected by the editor
                points = []
                for point in mask:
                    points.append({'x': int(point[0]), 'y': int(point[1])})

                # Apply simplification if threshold is set
                if simplification_threshold > 0:
                    points = simplify_points(points, simplification_threshold)

                if len(points) >= 3:  # Only add if it's a valid polygon
                    regions.append({'points': points})
        elif result.boxes is not None:
            # Process bounding boxes if no masks available (fallback)
            boxes = result.boxes.xyxy.cpu().numpy()  # x1, y1, x2, y2
            for box in boxes:
                x1, y1, x2, y2 = map(int, box)
                # Create a rectangular polygon from the bounding box
                points = [
                    {'x': x1, 'y': y1},
                    {'x': x2, 'y': y1},
                    {'x': x2, 'y': y2},
                    {'x': x1, 'y': y2}
                ]

                # Apply simplification if threshold is set
                if simplification_threshold > 0:
                    points = simplify_points(points, simplification_threshold)

                regions.append({'points': points})

    # Optionally merge overlapping regions
    if merge_overlapping:
        regions = merge_overlapping_regions(regions, overlap_threshold)

    return regions

def initialize_trocr_model(model_name="raxtemur/trocr-base-ru"):
    """
    Initialize the TROCR model at application startup
    """
    global trocr_model, trocr_processor

    if not TROCR_AVAILABLE:
        raise Exception("Transformers not available. Install transformers to enable text recognition.")

    # Check for available device
    import torch
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    print("Loading TROCR model...")
    trocr_processor = TrOCRProcessor.from_pretrained(model_name)
    trocr_model = VisionEncoderDecoderModel.from_pretrained(model_name)

    # Move model to device
    trocr_model = trocr_model.to(device)
    print("TROCR model loaded successfully")

    return device


def recognize_text_in_region(image, bbox, padding=10):
    """
    Recognize text in a specific region of the image using TROCR
    """
    global trocr_model, trocr_processor

    if trocr_model is None or trocr_processor is None:
        initialize_trocr_model()

    # Extract the region from the image with some padding
    left, top, right, bottom = bbox
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width, right + padding)
    bottom = min(image.height, bottom + padding)

    cropped_image = image.crop((left, top, right, bottom))
    print(f"  Cropped region with size: {cropped_image.size}")

    # Preprocess the cropped image
    pixel_values = trocr_processor(cropped_image, return_tensors="pt").pixel_values

    # Move pixel values to the appropriate device
    import torch
    device = next(trocr_model.parameters()).device  # Get the device the model is on
    pixel_values = pixel_values.to(device)

    # Generate text with TROCR
    print(f"  Processing with TROCR model...")
    generated_ids = trocr_model.generate(pixel_values)
    text = trocr_processor.batch_decode(generated_ids, skip_special_tokens=True)[0]
    print(f"  Recognition result: '{text}'")

    return text


def recognize_text_with_trocr(filename, regions=None, progress_callback=None):
    """
    Process image regions with TROCR to recognize text
    """
    global trocr_model, trocr_processor

    if not TROCR_AVAILABLE:
        raise Exception("Transformers not available. Install transformers to enable text recognition.")

    if trocr_model is None or trocr_processor is None:
        initialize_trocr_model()

    print(f"Starting text recognition for file: {filename}")

    # Load the image
    image_path = os.path.join(storage.IMAGE_FOLDER, filename)
    image = Image.open(image_path).convert("RGB")
    print(f"Loaded image: {image_path} with size {image.size}")

    # Load existing annotation data
    annotation_data = storage.load_json(filename)

    # If no regions specified, process all regions in the annotation
    if regions is None:
        regions = annotation_data.get('regions', [])

    print(f"Processing {len(regions)} regions for text recognition")

    # Process all regions
    recognized_texts = {}
    total_regions = len(regions)

    for idx, region in enumerate(regions):
        try:
            # Calculate bounding box for the region
            xs = [p['x'] for p in region['points']]
            ys = [p['y'] for p in region['points']]
            bbox = (min(xs), min(ys), max(xs), max(ys))

            print(f"Processing region {idx + 1}/{total_regions}: bbox={bbox}")

            # Recognize text in the region
            text = recognize_text_in_region(image, bbox)
            print(f"Recognized text for region {idx + 1}: '{text[:50]}{'...' if len(text) > 50 else ''}'")

            # Store the recognized text
            recognized_texts[idx] = text

            # Update progress if callback is provided
            if progress_callback:
                progress_callback(idx + 1, total_regions)
                print(f"Progress update: {idx + 1}/{total_regions} regions processed")
        except Exception as e:
            print(f"Error processing region {idx + 1}: {e}")
            recognized_texts[idx] = ""  # Store empty string in case of error

    print(f"Completed text recognition for {filename}, recognized text for {len([t for t in recognized_texts.values() if t])} out of {total_regions} regions")

    # Update the annotation data with recognized texts
    annotation_data['texts'] = recognized_texts

    # Save the updated annotation
    storage.save_json(annotation_data)

    return recognized_texts


# --- Task Management System ---
class TaskManager:
    def __init__(self):
        self.tasks = {}

    def create_task(self, task_id, task_type, project_name, images, description=""):
        """Create a new background task"""
        self.tasks[task_id] = {
            'id': task_id,
            'type': task_type,
            'project_name': project_name,
            'images': images,
            'description': description,
            'status': 'pending',  # pending, running, completed, failed
            'progress': 0,
            'total': len(images),
            'completed': 0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        return task_id

    def update_task_progress(self, task_id, completed, status=None):
        """Update the progress of a task"""
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task['completed'] = completed
            task['progress'] = int((completed / task['total']) * 100) if task['total'] > 0 else 0
            task['updated_at'] = datetime.now().isoformat()
            if status:
                task['status'] = status
            return task
        return None

    def get_task(self, task_id):
        """Get a specific task"""
        return self.tasks.get(task_id)

    def get_all_tasks(self):
        """Get all tasks"""
        return list(self.tasks.values())

    def delete_task(self, task_id):
        """Delete a task"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            return True
        return False

# Initialize the task manager
task_manager = TaskManager()


def run_batch_detection_for_project(project_name, settings=None):
    """
    Run batch detection for all images in a project
    """
    if settings is None:
        settings = {}

    # Get all images in the project
    from storage import get_project_images
    images = get_project_images(project_name)

    if not images:
        print(f"No images found in project {project_name}")
        return

    # Create a task for this batch operation
    import uuid
    task_id = str(uuid.uuid4())
    task_manager.create_task(
        task_id=task_id,
        task_type="batch_detection",
        project_name=project_name,
        images=images,
        description=f"Batch detection for project {project_name}"
    )

    # Update task status to running
    task_manager.update_task_progress(task_id, 0, "running")

    try:
        # Process each image
        for idx, image_name in enumerate(images):
            # Check if the image already has regions
            json_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('regions'):
                        # Skip if regions already exist, but update progress
                        task_manager.update_task_progress(task_id, idx + 1)
                        continue

            # Run detection on the image
            try:
                regions = detect_text_lines_yolo(image_name, settings)

                # Load existing annotation data or create new
                annotation_data = storage.load_json(image_name)
                annotation_data['regions'] = regions
                annotation_data['status'] = 'cropped'  # Mark as segmented

                # Save the updated annotation
                storage.save_json(annotation_data)

                # Update task progress
                task_manager.update_task_progress(task_id, idx + 1)

            except Exception as e:
                print(f"Error detecting lines in {image_name}: {e}")
                # Still update progress even if there's an error
                task_manager.update_task_progress(task_id, idx + 1)

        # Mark task as completed
        task_manager.update_task_progress(task_id, len(images), "completed")
        print(f"Batch detection completed for project {project_name}")

    except Exception as e:
        print(f"Error in batch detection for project {project_name}: {e}")
        task_manager.update_task_progress(task_id, 0, "failed")


def run_batch_recognition_for_project(project_name):
    """
    Run batch recognition for all images in a project
    """
    # Get all images in the project
    from storage import get_project_images
    images = get_project_images(project_name)

    if not images:
        print(f"No images found in project {project_name}")
        return

    # Create a task for this batch operation
    import uuid
    task_id = str(uuid.uuid4())
    task_manager.create_task(
        task_id=task_id,
        task_type="batch_recognition",
        project_name=project_name,
        images=images,
        description=f"Batch recognition for project {project_name}"
    )

    # Update task status to running
    task_manager.update_task_progress(task_id, 0, "running")

    try:
        # Process each image
        for idx, image_name in enumerate(images):
            # Check if the image already has recognized text
            json_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')
            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('texts'):
                        # Skip if texts already exist, but update progress
                        task_manager.update_task_progress(task_id, idx + 1)
                        continue

            # Run recognition on the image
            try:
                recognize_text_with_trocr(image_name, None)  # Process all regions

                # Update task progress
                task_manager.update_task_progress(task_id, idx + 1)

            except Exception as e:
                print(f"Error recognizing text in {image_name}: {e}")
                # Still update progress even if there's an error
                task_manager.update_task_progress(task_id, idx + 1)

        # Mark task as completed
        task_manager.update_task_progress(task_id, len(images), "completed")
        print(f"Batch recognition completed for project {project_name}")

    except Exception as e:
        print(f"Error in batch recognition for project {project_name}: {e}")
        task_manager.update_task_progress(task_id, 0, "failed")