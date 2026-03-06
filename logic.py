"""
Logic module for HTR Annotation Tool.

Contains:
- Mathematical functions for coordinate transformations
- Image processing helpers
- AI model integration (YOLOv9, TROCR)
- Batch processing functions
- ZIP import/export helpers

Note: Most business logic has been moved to the services layer.
This module now focuses on low-level operations.
"""

import os
import math
import zipfile
import shutil
import threading
import xml.etree.ElementTree as ET
import json
from PIL import Image, ImageOps
from datetime import datetime

import storage
import config

# YOLOv9 imports
try:
    import torch
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# TROCR imports
try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False


# =============================================================================
# Mathematical functions for coordinate transformations
# =============================================================================

def recalculate_regions(regions, old_crop, new_crop_params, new_w, new_h):
    """
    Масштабирует регионы: Локальные(старые) -> Глобальные -> Локальные(новые).
    """
    if not regions:
        return []

    def lerp_quad(u, v, c):
        # c: [TL, TR, BR, BL]
        x = (1-u)*(1-v)*c[0]['x'] + u*(1-v)*c[1]['x'] + u*v*c[2]['x'] + (1-u)*v*c[3]['x']
        y = (1-u)*(1-v)*c[0]['y'] + u*(1-v)*c[1]['y'] + u*v*c[2]['y'] + (1-u)*v*c[3]['y']
        return x, y

    def get_uv(px, py, c):
        v_top = (c[1]['x'] - c[0]['x'], c[1]['y'] - c[0]['y'])
        v_left = (c[3]['x'] - c[0]['x'], c[3]['y'] - c[0]['y'])
        v_p = (px - c[0]['x'], py - c[0]['y'])

        def dot_ratio(v, p_v):
            mag_sq = v[0]**2 + v[1]**2
            if mag_sq == 0:
                return 0
            return (p_v[0]*v[0] + p_v[1]*v[1]) / mag_sq

        return dot_ratio(v_top, v_p), dot_ratio(v_left, v_p)

    has_old_crop = old_crop and 'corners' in old_crop
    if has_old_crop:
        oc = old_crop['corners']
        ow = math.sqrt((oc[1]['x']-oc[0]['x'])**2 + (oc[1]['y']-oc[0]['y'])**2)
        oh = math.sqrt((oc[3]['x']-oc[0]['x'])**2 + (oc[3]['y']-oc[0]['y'])**2)

    final_regions = []
    for reg in regions:
        new_points = []
        for p in reg['points']:
            if has_old_crop:
                u_old, v_old = p['x'] / ow, p['y'] / oh
                gx, gy = lerp_quad(u_old, v_old, oc)
            else:
                gx, gy = p['x'], p['y']

            u_new, v_new = get_uv(gx, gy, new_crop_params)
            final_x = u_new * new_w
            final_y = v_new * new_h

            new_points.append({'x': int(round(final_x)), 'y': int(round(final_y))})
        final_regions.append({'points': new_points})

    return final_regions


def perform_crop(filename, box):
    """
    Perform crop operation on an image.
    This function is kept for backward compatibility.
    New code should use ImageService.crop_image() instead.
    """
    if not storage.ensure_original_exists(filename):
        return False
    
    src_path = os.path.join(storage.IMAGE_FOLDER, filename)
    backup_path = os.path.join(storage.ORIGINALS_FOLDER, filename)

    try:
        json_data = storage.load_json(filename)
        old_crop = json_data.get('crop_params')
        old_regions = json_data.get('regions', [])

        with Image.open(backup_path) as img:
            img = ImageOps.exif_transpose(img)
            c = box['corners']

            quad = [c[0]['x'], c[0]['y'], c[3]['x'], c[3]['y'],
                    c[2]['x'], c[2]['y'], c[1]['x'], c[1]['y']]

            def dist(p1, p2):
                return math.sqrt((p1['x']-p2['x'])**2 + (p1['y']-p2['y'])**2)
            
            nw = int((dist(c[0], c[1]) + dist(c[3], c[2])) / 2)
            nh = int((dist(c[0], c[3]) + dist(c[1], c[2])) / 2)

            img_cropped = img.transform((nw, nh), Image.QUAD, quad, Image.BICUBIC)
            img_cropped.save(src_path)

            new_regions = recalculate_regions(old_regions, old_crop, c, nw, nh)

            json_data['regions'] = new_regions
            json_data['crop_params'] = box
            json_data['status'] = 'cropped'
            json_data['image_name'] = filename

            storage.save_json(json_data)
        return True
    except Exception as e:
        print(f"Crop Error: {e}")
        return False


# =============================================================================
# Polygon helpers
# =============================================================================

def simplify_points(points, threshold):
    """Simplify polygon by removing points closer than threshold."""
    if not points or threshold <= 0:
        return points
    
    new_p = [points[0]]
    for p in points[1:]:
        if math.hypot(p['x']-new_p[-1]['x'], p['y']-new_p[-1]['y']) >= threshold:
            new_p.append(p)
    
    if points[-1] != new_p[-1]:
        new_p.append(points[-1])
    
    return new_p


def calculate_polygon_area(points):
    """Calculate the area of a polygon using the Shoelace formula."""
    if len(points) < 3:
        return 0

    area = 0
    n = len(points)

    for i in range(n):
        j = (i + 1) % n
        area += points[i]['x'] * points[j]['y']
        area -= points[j]['x'] * points[i]['y']

    return abs(area) / 2


def calculate_overlap_ratio(points1, points2):
    """
    Calculate the overlap ratio between two polygons.
    Uses Jaccard similarity (intersection over union).
    """
    min_x1 = min(p['x'] for p in points1)
    max_x1 = max(p['x'] for p in points1)
    min_y1 = min(p['y'] for p in points1)
    max_y1 = max(p['y'] for p in points1)

    min_x2 = min(p['x'] for p in points2)
    max_x2 = max(p['x'] for p in points2)
    min_y2 = min(p['y'] for p in points2)
    max_y2 = max(p['y'] for p in points2)

    inter_x1 = max(min_x1, min_x2)
    inter_y1 = max(min_y1, min_y2)
    inter_x2 = min(max_x1, max_x2)
    inter_y2 = min(max_y1, max_y2)

    if inter_x1 < inter_x2 and inter_y1 < inter_y2:
        intersection_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
        area1 = calculate_polygon_area(points1)
        area2 = calculate_polygon_area(points2)
        union_area = area1 + area2 - intersection_area
        
        if union_area > 0:
            return (intersection_area / union_area) * 100
    
    return 0


def are_regions_spatially_close(points1, points2):
    """Check if two regions are spatially close to each other."""
    centroid1_x = sum(p['x'] for p in points1) / len(points1)
    centroid1_y = sum(p['y'] for p in points1) / len(points1)
    centroid2_x = sum(p['x'] for p in points2) / len(points2)
    centroid2_y = sum(p['y'] for p in points2) / len(points2)

    distance = math.sqrt((centroid1_x - centroid2_x)**2 + (centroid1_y - centroid2_y)**2)

    width1 = max(p['x'] for p in points1) - min(p['x'] for p in points1)
    height1 = max(p['y'] for p in points1) - min(p['y'] for p in points1)
    size1 = math.sqrt(width1 * height1)

    width2 = max(p['x'] for p in points2) - min(p['x'] for p in points2)
    height2 = max(p['y'] for p in points2) - min(p['y'] for p in points2)
    size2 = math.sqrt(width2 * height2)

    avg_size = (size1 + size2) / 2

    return distance < avg_size * 3


def convex_hull(points):
    """Find the convex hull of a set of points using Graham scan algorithm."""
    def polar_angle(p0, p1):
        if p0['x'] == p1['x']:
            return float('inf')
        return math.atan2(p1['y'] - p0['y'], p1['x'] - p0['x'])

    def distance_squared(p0, p1):
        return (p1['x'] - p0['x']) ** 2 + (p1['y'] - p0['y']) ** 2

    def cross_product(o, a, b):
        return (a['x'] - o['x']) * (b['y'] - o['y']) - (a['y'] - o['y']) * (b['x'] - o['x'])

    start = min(points, key=lambda p: (p['y'], p['x']))
    sorted_points = sorted(points, key=lambda p: (polar_angle(start, p), distance_squared(start, p)))

    hull = []
    for point in sorted_points:
        while len(hull) > 1 and cross_product(hull[-2], hull[-1], point) <= 0:
            hull.pop()
        hull.append(point)

    return hull


def merge_two_polygons(points1, points2):
    """Merge two polygons using convex hull."""
    all_points = points1 + points2
    hull_points = convex_hull(all_points)
    return {'points': hull_points}


def merge_overlapping_regions(regions, overlap_threshold=30):
    """
    Merge overlapping regions in the list based on overlap threshold.
    overlap_threshold: percentage of area overlap required to merge regions
    """
    if not regions:
        return regions

    unprocessed_regions = [r.copy() for r in regions]
    merged_regions = []

    while unprocessed_regions:
        current_region = unprocessed_regions.pop(0)
        regions_to_merge = []
        
        for other_region in unprocessed_regions[:]:
            overlap_ratio = calculate_overlap_ratio(current_region['points'], other_region['points'])
            is_spatially_close = are_regions_spatially_close(current_region['points'], other_region['points'])

            if overlap_ratio >= overlap_threshold and is_spatially_close:
                regions_to_merge.append(other_region)

        final_region = current_region
        for region_to_merge in regions_to_merge:
            final_region = merge_two_polygons(final_region['points'], region_to_merge['points'])
            unprocessed_regions.remove(region_to_merge)

        merged_regions.append(final_region)

    return merged_regions


# =============================================================================
# Import/Export helpers
# =============================================================================

def parse_page_xml(xml_path, simplify_val):
    """Parse PAGE XML file and extract regions and texts."""
    regions = []
    texts = {}
    
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {'p': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        prefix = 'p:' if ns else ''
        
        for i, line in enumerate(root.findall(f'.//{prefix}TextLine', ns)):
            coords = line.find(f'{prefix}Coords', ns)
            if coords is not None and coords.get('points'):
                pts = []
                for pair in coords.get('points').strip().split():
                    try:
                        x, y = map(float, pair.split(','))
                        pts.append({'x': int(x), 'y': int(y)})
                    except:
                        continue
                
                if pts:
                    if simplify_val > 0:
                        pts = simplify_points(pts, simplify_val)
                    regions.append({'points': pts})

                    text_equiv = line.find(f'{prefix}TextEquiv', ns)
                    if text_equiv is not None:
                        unicode_elem = text_equiv.find(f'{prefix}Unicode', ns)
                        if unicode_elem is not None and unicode_elem.text:
                            texts[str(i)] = unicode_elem.text
                    else:
                        texts[str(i)] = ''
                        
    except Exception as e:
        print(f"XML Error: {e}")
    
    return regions, texts


def process_zip_import(file, simplify_val=0, project_name=None):
    """
    Import ZIP archive into a project.
    If project_name is not specified, creates a new project.
    """
    import uuid
    from services.project_service import project_service

    if project_name is None:
        original_filename = file.filename
        project_name = os.path.splitext(original_filename)[0] + "_" + str(uuid.uuid4())[:8]
        success, result = project_service.create_project(project_name)

        if not success:
            raise Exception(f"Failed to create project: {result}")

    # Use sanitized name for path
    project_path = os.path.join(storage.PROJECTS_FOLDER, project_service._sanitize_name(project_name))

    if not os.path.exists(project_path):
        raise Exception(f"Project {project_name} does not exist")

    zip_path = os.path.join(storage.TEMP_FOLDER, 'import.zip')
    file.save(zip_path)
    
    extract_path = os.path.join(storage.TEMP_FOLDER, 'ext')
    if os.path.exists(extract_path):
        shutil.rmtree(extract_path)
    os.makedirs(extract_path)

    count = 0
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            z.extractall(extract_path)

        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith(tuple(storage.ALLOWED_EXTENSIONS)):
                    src = os.path.join(root, f)
                    dest_path = os.path.join(storage.IMAGE_FOLDER, f)
                    shutil.move(src, dest_path)

                    xml_cands = [os.path.splitext(src)[0]+'.xml', src+'.xml']
                    for xc in xml_cands:
                        if os.path.exists(xc):
                            regs, texts = parse_page_xml(xc, simplify_val)

                            json_data = {'image_name': f, 'regions': regs, 'texts': texts}
                            json_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(f)[0] + '.json')

                            with open(json_path, 'w', encoding='utf-8') as jf:
                                json.dump(json_data, jf, indent=4)

                            # Add image to project using service
                            project_service.add_image(project_name, f)
                            break
                    count += 1
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
        if os.path.exists(extract_path):
            shutil.rmtree(extract_path)

    return count, project_name


# =============================================================================
# Batch processing functions
# =============================================================================

def run_batch_detection_for_project(project_name, settings=None, task_id=None):
    """
    Run batch detection for all images in a project.
    
    Args:
        project_name: Project name
        settings: YOLO detection settings
        task_id: Task ID from task_service (passed by app.py)
    """
    if settings is None:
        settings = {}

    images = storage.get_project_images(project_name)

    if not images:
        print(f"No images found in project {project_name}")
        return

    # Use task_service from services layer
    from services import task_service, ai_service, annotation_service

    # Get task by ID (passed from app.py)
    if not task_id:
        print(f"Error: task_id not provided for batch detection")
        return

    task = task_service.get_task(task_id)
    if not task:
        print(f"Error: task {task_id} not found")
        return

    try:
        task_service.update_progress(task.id, 0, status="running")

        for idx, image_name in enumerate(images):
            json_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')

            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('regions'):
                        task_service.update_progress(task.id, idx + 1)
                        continue

            try:
                regions = ai_service.detect_lines(image_name, settings)

                annotation_data = storage.load_json(image_name)
                annotation_data['regions'] = regions
                if annotation_data.get('status') != 'cropped':
                    annotation_data['status'] = 'segment'

                storage.save_json(annotation_data)
                task_service.update_progress(task.id, idx + 1)

            except Exception as e:
                print(f"Error detecting lines in {image_name}: {e}")
                task_service.update_progress(task.id, idx + 1)

        task_service.update_progress(task.id, len(images), status="completed")
        print(f"Batch detection completed for project {project_name}")

    except Exception as e:
        print(f"Error in batch detection for project {project_name}: {e}")
        task_service.fail_task(task.id, str(e))


def run_batch_recognition_for_project(project_name, task_id=None):
    """
    Run batch recognition for all images in a project.
    
    Args:
        project_name: Project name
        task_id: Task ID from task_service (passed by app.py)
    """
    images = storage.get_project_images(project_name)

    if not images:
        print(f"No images found in project {project_name}")
        return

    # Use task_service from services layer
    from services import task_service, ai_service

    # Get task by ID (passed from app.py)
    if not task_id:
        print(f"Error: task_id not provided for batch recognition")
        return

    task = task_service.get_task(task_id)
    if not task:
        print(f"Error: task {task_id} not found")
        return

    try:
        task_service.update_progress(task.id, 0, status="running")

        for idx, image_name in enumerate(images):
            json_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')

            if os.path.exists(json_path):
                with open(json_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get('texts'):
                        task_service.update_progress(task.id, idx + 1)
                        continue

            try:
                ai_service.recognize_text(image_name, None)
                task_service.update_progress(task.id, idx + 1)

            except Exception as e:
                print(f"Error recognizing text in {image_name}: {e}")
                task_service.update_progress(task.id, idx + 1)

        task_service.update_progress(task.id, len(images), status="completed")
        print(f"Batch recognition completed for project {project_name}")

    except Exception as e:
        print(f"Error in batch recognition for project {project_name}: {e}")
        task_service.fail_task(task.id, str(e))


# =============================================================================
# Task Manager deprecated - use services/task_service.py instead
# =============================================================================
# The TaskManager class and task_manager instance have been removed.
# All code should now use services.task_service instead.
