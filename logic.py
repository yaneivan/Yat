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

import logging
import os
import math
import zipfile
import shutil
import xml.etree.ElementTree as ET

import storage
from database.enums import ImageStatus, TaskStatus

# Configure logging
logger = logging.getLogger(__name__)

# YOLOv9 imports
try:
    import torch  # noqa: F401
    from ultralytics import YOLO  # noqa: F401
    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

# TROCR imports
try:
    from transformers import (  # noqa: F401
        TrOCRProcessor,
        VisionEncoderDecoderModel,
    )
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


def calculate_overlap_ratio(points1, points2, use_min_area=False):
    """
    Calculate the overlap ratio between two polygons.
    
    Args:
        points1, points2: Polygon points
        use_min_area: If True, use intersection/min_area instead of IoU.
                      This is better for detecting when a small segment 
                      overlaps significantly with a larger one.
    
    Returns:
        Overlap ratio as percentage (0-100)
    """
    try:
        from shapely.geometry import Polygon
        
        poly1 = Polygon([(p['x'], p['y']) for p in points1])
        poly2 = Polygon([(p['x'], p['y']) for p in points2])
        
        if not poly1.is_valid or not poly2.is_valid:
            pass  # Fallback to bounding box method below
        else:
            intersection = poly1.intersection(poly2).area
            area1 = poly1.area
            area2 = poly2.area
            
            if area1 <= 0 or area2 <= 0:
                return 0
            
            if use_min_area:
                # Use min area - better for small-inside-large detection
                min_area = min(area1, area2)
                if min_area > 0:
                    return (intersection / min_area) * 100
            else:
                # Use IoU (Jaccard) - symmetric
                union = poly1.union(poly2).area
                if union > 0:
                    return (intersection / union) * 100
    except ImportError:
        pass  # Fallback to bounding box method below
    except Exception:
        pass  # Fallback to bounding box method below
    
    # Fallback: bounding box approximation
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
        
        if use_min_area:
            min_area = min(area1, area2)
            if min_area > 0:
                return (intersection_area / min_area) * 100
        else:
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
    """
    Merge two polygons using shapely.union for proper shape preservation.
    Returns the unified polygon points or None if merge fails.
    """
    try:
        from shapely.geometry import Polygon, MultiPolygon
        
        poly1 = Polygon([(p['x'], p['y']) for p in points1])
        poly2 = Polygon([(p['x'], p['y']) for p in points2])
        
        if not poly1.is_valid or not poly2.is_valid:
            return None
        
        # Perform union
        result = poly1.union(poly2)
        
        # Handle different result types
        if isinstance(result, Polygon):
            # Single polygon - extract points
            if result.is_empty:
                return None
            return {'points': [{'x': int(x), 'y': int(y)} for x, y in result.exterior.coords[:-1]]}
        elif isinstance(result, MultiPolygon):
            # Multiple polygons - return the largest one (most likely the merged one)
            largest = max(result.geoms, key=lambda p: p.area)
            return {'points': [{'x': int(x), 'y': int(y)} for x, y in largest.exterior.coords[:-1]]}
        else:
            return None
            
    except ImportError:
        # Fallback to convex hull if shapely not available
        all_points = points1 + points2
        hull_points = convex_hull(all_points)
        return {'points': hull_points}
    except Exception:
        return None


def _get_polygon_bounds(points):
    """Get bounding box and centroid of polygon."""
    xs = [p['x'] for p in points]
    ys = [p['y'] for p in points]
    return {
        'min_x': min(xs),
        'max_x': max(xs),
        'min_y': min(ys),
        'max_y': max(ys),
        'centroid_x': sum(xs) / len(xs),
        'centroid_y': sum(ys) / len(ys),
        'width': max(xs) - min(xs),
        'height': max(ys) - min(ys)
    }


def _should_merge_horizontally(bounds1, bounds2, height_ratio_threshold=2.0):
    """
    Check if two polygons should be merged based on horizontal alignment.
    
    Returns True if:
    - Polygons are horizontally aligned (similar Y positions)
    - Merging won't create an excessively tall polygon
    
    Returns False if:
    - Polygons are vertically separated (different text lines)
    - Merging would create a polygon that's too tall
    """
    # Check vertical separation - if centroids are far apart in Y, don't merge
    y_centroid_diff = abs(bounds1['centroid_y'] - bounds2['centroid_y'])
    avg_height = (bounds1['height'] + bounds2['height']) / 2
    
    # If vertical distance between centroids is more than average height,
    # they're likely on different lines
    if y_centroid_diff > avg_height * 0.7:
        return False
    
    # Check if bounding boxes overlap significantly in Y dimension
    y_overlap = max(0, min(bounds1['max_y'], bounds2['max_y']) - max(bounds1['min_y'], bounds2['min_y']))
    min_y_overlap = min(bounds1['height'], bounds2['height']) * 0.3  # At least 30% height overlap
    
    if y_overlap < min_y_overlap:
        return False
    
    return True


def calculate_containment(inner, outer):
    """
    Calculate how much of the 'inner' polygon is contained within the 'outer' polygon.
    Uses shapely's covered_by for accurate geometric calculation.
    
    Returns:
        float: Containment ratio (0.0 to 1.0)
        1.0 = inner is completely inside outer
        0.0 = inner is completely outside outer
    """
    try:
        from shapely.geometry import Polygon
        
        poly_inner = Polygon([(p['x'], p['y']) for p in inner])
        poly_outer = Polygon([(p['x'], p['y']) for p in outer])
        
        if not poly_inner.is_valid or not poly_outer.is_valid:
            return 0.0
        
        # Use shapely's built-in coverage check
        if poly_inner.covered_by(poly_outer):
            return 1.0
        
        # Partial containment: intersection / inner area
        intersection = poly_inner.intersection(poly_outer).area
        inner_area = poly_inner.area
        
        if inner_area <= 0:
            return 0.0
        
        return intersection / inner_area
        
    except ImportError:
        return 0.0
    except Exception:
        return 0.0


def remove_duplicate_regions(regions, containment_threshold=0.9):
    """
    Remove segments that are almost completely contained within larger segments.
    
    This handles the case where a small segment is inside a large one -
    instead of merging, we remove the small one as it's likely a detection duplicate.
    
    Args:
        regions: List of region dicts with 'points'
        containment_threshold: If >90% of region A is inside region B, remove A
    
    Returns:
        Filtered list of regions
    """
    if not regions:
        return regions
    
    result = []
    
    for i, region in enumerate(regions):
        is_contained = False
        region_area = calculate_polygon_area(region['points'])
        
        for j, other in enumerate(regions):
            if i == j:
                continue
            
            other_area = calculate_polygon_area(other['points'])
            
            # Only check if 'other' is significantly larger
            if other_area <= region_area:
                continue
            
            # Check how much 'region' is contained in 'other'
            containment = calculate_containment(region['points'], other['points'])
            
            if containment > containment_threshold:
                is_contained = True
                break
        
        if not is_contained:
            result.append(region)
    
    return result


def merge_overlapping_regions(regions, overlap_threshold=50):
    """
    Merge overlapping regions in the list based on overlap threshold.

    Key improvements:
    1. Uses shapely.union instead of convex hull for proper shape preservation
    2. Prevents vertical merging of different text lines
    3. Checks aspect ratio to avoid creating "blobs"
    4. Uses min-area overlap (not IoU) to detect small-inside-large cases

    overlap_threshold: percentage of area overlap required to merge regions (default 50%)
    """
    if not regions:
        return regions

    unprocessed_regions = [r.copy() for r in regions]
    merged_regions = []

    while unprocessed_regions:
        current_region = unprocessed_regions.pop(0)
        current_bounds = _get_polygon_bounds(current_region['points'])
        regions_to_merge = []

        for other_region in unprocessed_regions[:]:
            # Use min_area=True to detect small-inside-large overlaps
            overlap_ratio = calculate_overlap_ratio(
                current_region['points'], 
                other_region['points'],
                use_min_area=True
            )
            other_bounds = _get_polygon_bounds(other_region['points'])

            # Check if regions should be merged horizontally
            can_merge_horizontally = _should_merge_horizontally(current_bounds, other_bounds)

            # Only merge if:
            # 1. Overlap ratio is above threshold
            # 2. Regions are horizontally aligned (same text line)
            if overlap_ratio >= overlap_threshold and can_merge_horizontally:
                regions_to_merge.append(other_region)

        final_region = current_region
        for region_to_merge in regions_to_merge:
            # Try to merge using shapely
            merged = merge_two_polygons(final_region['points'], region_to_merge['points'])

            if merged:
                # Check if merged polygon is reasonable (not too tall)
                merged_bounds = _get_polygon_bounds(merged['points'])
                original_max_height = max(current_bounds['height'],
                                         _get_polygon_bounds(region_to_merge['points'])['height'])

                # If merged height is more than 2x the original, skip this merge
                if merged_bounds['height'] <= original_max_height * 2.0:
                    final_region = merged
                    unprocessed_regions.remove(region_to_merge)
                # else: don't merge - it would create a "blob"

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
                    except (ValueError, TypeError, AttributeError):
                        # Skip malformed coordinate pairs
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
        logger.error(f"XML Error: {e}")

    return regions, texts


def process_zip_import(file, simplify_val=0, project_name=None):
    """
    Import ZIP archive into a project.
    If project_name is not specified, creates a new project.
    """
    import uuid
    from services.project_service import project_service
    from services.annotation_service import annotation_service

    if project_name is None:
        original_filename = file.filename
        project_name = os.path.splitext(original_filename)[0] + "_" + str(uuid.uuid4())[:8]
        result = project_service.create_project(project_name)

        if not result:
            raise Exception(f"Failed to create project: {project_name}")

    zip_path = os.path.join(storage.TEMP_FOLDER, 'import.zip')
    file.save(zip_path)

    extract_path = os.path.join(storage.TEMP_FOLDER, 'ext')
    if os.path.exists(extract_path):
        shutil.rmtree(extract_path)
    os.makedirs(extract_path)

    count = 0

    try:
        with zipfile.ZipFile(zip_path, 'r') as z:
            # Zip Slip vulnerability fix: validate all paths before extraction
            for member in z.namelist():
                member_path = os.path.join(extract_path, member)
                # Check that the extracted file will be within extract_path
                if not os.path.abspath(member_path).startswith(os.path.abspath(extract_path)):
                    raise Exception(f"Zip Slip detected: {member}")
            
            z.extractall(extract_path)

        for root, _, files in os.walk(extract_path):
            for f in files:
                if f.lower().endswith(tuple(storage.ALLOWED_EXTENSIONS)):
                    src = os.path.join(root, f)
                    dest_path = os.path.join(storage.IMAGE_FOLDER, f)
                    shutil.move(src, dest_path)

                    # Copy to originals folder
                    original_dest = os.path.join(storage.ORIGINALS_FOLDER, f)
                    shutil.copy(dest_path, original_dest)

                    xml_cands = [os.path.splitext(src)[0]+'.xml', src+'.xml']
                    for xc in xml_cands:
                        if os.path.exists(xc):
                            regs, texts = parse_page_xml(xc, simplify_val)

                            # Сначала добавляем изображение в проект (создаётся в БД)
                            project_service.add_image(
                                project_name=project_name,
                                filename=f,
                                original_path=original_dest,
                                cropped_path=dest_path,
                                status=ImageStatus.SEGMENTED,
                                crop_params=None
                            )

                            # Потом сохраняем аннотацию (теперь image есть в БД)
                            annotation_data = {
                                'image_name': f,
                                'regions': regs,
                                'texts': texts,
                                'status': ImageStatus.SEGMENTED.value
                            }
                            annotation_service.save_annotation(f, annotation_data, project_name)
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

    # Use project_service to get images from database
    from services import project_service, task_service, ai_service, annotation_service

    images = project_service.get_images(project_name)
    
    if not images:
        logger.warning(f"No images found in project {project_name}")
        return

    # Get task by ID (passed from app.py)
    if not task_id:
        logger.error("Error: task_id not provided for batch detection")
        return

    task = task_service.get_task(task_id)
    if not task:
        logger.error(f"Error: task {task_id} not found")
        return

    # Extract image names from image data dicts
    image_names = [img.get('filename') or img.get('name') if isinstance(img, dict) else img for img in images]

    try:
        task_service.update_progress(task.id, 0, status=TaskStatus.RUNNING)

        for idx, image_name in enumerate(image_names):
            # Check if annotation already has regions using annotation_service
            annotation_data = annotation_service.get_annotation(image_name, project_name)

            if annotation_data.get('regions'):
                task_service.update_progress(task.id, idx + 1)
                continue

            try:
                regions = ai_service.detect_lines(image_name, settings)

                # Use annotation_service instead of old storage layer
                annotation_data = annotation_service.get_annotation(image_name, project_name)
                annotation_data['regions'] = regions
                if annotation_data.get('status') != ImageStatus.CROPPED.value:
                    annotation_data['status'] = ImageStatus.SEGMENTED.value

                annotation_service.save_annotation(image_name, annotation_data, project_name)
                task_service.update_progress(task.id, idx + 1)

            except Exception as e:
                logger.error(f"Error detecting lines in {image_name}: {e}")
                task_service.update_progress(task.id, idx + 1)

        task_service.update_progress(task.id, len(image_names), status=TaskStatus.COMPLETED)
        logger.info(f"Batch detection completed for project {project_name}")

    except Exception as e:
        logger.error(f"Error in batch detection for project {project_name}: {e}")
        task_service.fail_task(task.id, str(e))


def run_batch_recognition_for_project(project_name, task_id=None):
    """
    Run batch recognition for all images in a project.

    Args:
        project_name: Project name
        task_id: Task ID from task_service (passed by app.py)
    """
    # Use project_service to get images from database
    from services import project_service, task_service, ai_service, annotation_service

    images = project_service.get_images(project_name)
    if not images:
        logger.warning(f"No images found in project {project_name}")
        return

    # Get task by ID (passed from app.py)
    if not task_id:
        logger.error("Error: task_id not provided for batch recognition")
        return

    task = task_service.get_task(task_id)
    if not task:
        logger.error(f"Error: task {task_id} not found")
        return

    # Extract image names from image data dicts
    image_names = [img.get('filename') or img.get('name') if isinstance(img, dict) else img for img in images]

    try:
        task_service.update_progress(task.id, 0, status=TaskStatus.RUNNING)

        for idx, image_name in enumerate(image_names):
            # Check if annotation already has texts using annotation_service
            annotation_data = annotation_service.get_annotation(image_name, project_name)

            # Skip if no polygons (nothing to recognize)
            regions = annotation_data.get('regions', [])
            if not regions:
                logger.warning(f"Skip {image_name}: no polygons for recognition")
                task_service.update_progress(task.id, idx + 1)
                continue

            # Skip if text already recognized
            if annotation_data.get('texts') and any(annotation_data.get('texts', {}).values()):
                task_service.update_progress(task.id, idx + 1)
                continue

            try:
                ai_service.recognize_text(image_name, None)
                task_service.update_progress(task.id, idx + 1)

            except Exception as e:
                logger.error(f"Error recognizing text in {image_name}: {e}")
                task_service.update_progress(task.id, idx + 1)

        task_service.update_progress(task.id, len(image_names), status=TaskStatus.COMPLETED)
        logger.info(f"Batch recognition completed for project {project_name}")

    except Exception as e:
        logger.error(f"Error in batch recognition for project {project_name}: {e}")
        task_service.fail_task(task.id, str(e))


# =============================================================================
# Task Manager deprecated - use services/task_service.py instead
# =============================================================================
# The TaskManager class and task_manager instance have been removed.
# All code should now use services.task_service instead.
