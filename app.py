from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, send_file
import storage
import logic
import threading
import os
import json
import re
from datetime import datetime
import config

# Initialize TROCR model at startup
if logic.TROCR_AVAILABLE:
    try:
        device = logic.initialize_trocr_model("raxtemur/trocr-base-ru")  # Russian-specific model
        print(f"TROCR model initialized successfully on {device}")
    except Exception as e:
        print(f"Error initializing TROCR model: {e}")

app = Flask(__name__)

# --- Pages ---
@app.route('/')
def index():
    return render_template('index.html', files=storage.get_images_with_status())

@app.route('/editor')
def editor():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename: return redirect(url_for('index'))
    return render_template('editor.html', filename=filename, project=project_name)

@app.route('/text_editor')
def text_editor():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename: return redirect(url_for('index'))
    return render_template('text_editor.html', filename=filename, project=project_name)

@app.route('/cropper')
def cropper():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename: return redirect(url_for('index'))
    return render_template('cropper.html', filename=filename, project=project_name)

# --- API ---
@app.route('/api/images_list')
def list_images():
    return jsonify(storage.get_sorted_images())

@app.route('/data/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(storage.IMAGE_FOLDER, filename)

@app.route('/data/originals/<path:filename>')
def serve_original(filename):
    try:
        return send_from_directory(storage.ORIGINALS_FOLDER, filename)
    except:
        return send_from_directory(storage.IMAGE_FOLDER, filename)

@app.route('/api/load/<filename>')
def load_data(filename):
    return jsonify(storage.load_json(filename))

@app.route('/api/save', methods=['POST'])
def save_data():
    incoming_data = request.json
    filename = incoming_data.get('image_name')
    if not filename:
        return jsonify({'status': 'error', 'msg': 'No filename'}), 400

    # 1. Загружаем то, что уже лежит на диске
    existing_data = storage.load_json(filename)
    
    # 2. Обновляем поля (regions, texts и т.д.), но сохраняем crop_params
    for key in ['regions', 'texts', 'status', 'processing_params']:
        if key in incoming_data:
            existing_data[key] = incoming_data[key]
            
    # Не трогаем crop_params, если они уже есть в файле, а в новых данных их нет
    if 'crop_params' in incoming_data:
        existing_data['crop_params'] = incoming_data['crop_params']

    if storage.save_json(existing_data): 
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/upload', methods=['POST'])
def upload():
    count = sum(1 for f in request.files.getlist('files[]') if storage.save_image(f))
    return jsonify({'status': 'success', 'count': count})

@app.route('/api/delete', methods=['POST'])
def delete():
    count = storage.delete_file_set(request.json.get('filenames', []))
    return jsonify({'status': 'success', 'deleted': count})

@app.route('/api/crop', methods=['POST'])
def crop():
    data = request.json
    filename = data.get('image_name')
    box = data.get('box')
    
    if not filename or not box:
        return jsonify({'status': 'error', 'msg': 'No data'}), 400

    # Async background processing
    def task():
        logic.perform_crop(filename, box)
    
    thread = threading.Thread(target=task)
    thread.start()
    
    return jsonify({'status': 'success', 'msg': 'Background processing started'})

@app.route('/api/import_zip', methods=['POST'])
def import_zip_route():
    try:
        # Добавим логирование для отладки
        print("Form data:", request.form)
        print("Files:", request.files.keys())
        
        simp = int(request.form.get('simplify', 0))
        print("Simplify value:", simp)
        
        # Получаем необязательное имя проекта
        project_name = request.form.get('project_name', None)
        
        # Проверим, есть ли файл в запросе
        if 'file' not in request.files:
            print("No file in request")
            return jsonify({'status': 'error', 'msg': 'No file in request'}), 400
            
        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            print("No file selected")
            return jsonify({'status': 'error', 'msg': 'No file selected'}), 400
            
        # Вызываем универсальную функцию импорта
        count, final_project_name = logic.process_zip_import(uploaded_file, simp, project_name)
        return jsonify({'status': 'success', 'count': count, 'project_name': final_project_name})
    except Exception as e:
        print(f"Error in import_zip_route: {str(e)}")
        return jsonify({'status': 'error', 'msg': str(e)}), 500

@app.route('/api/export_zip')
def export_zip_route():
    try:
        return send_file(logic.generate_export_zip(), as_attachment=True, download_name='export.zip')
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/detect_lines', methods=['POST'])
def detect_lines():
    data = request.json
    filename = data.get('image_name')
    settings = data.get('settings', {})
    if not filename:
        return jsonify({'status': 'error', 'msg': 'No image name provided'}), 400

    print(f"Received settings: {settings}")  # Отладочный вывод

    try:
        from logic import detect_text_lines_yolo
        regions = detect_text_lines_yolo(filename, settings)
        return jsonify({'status': 'success', 'regions': regions})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

# Global dictionary to track recognition progress
recognition_progress = {}

@app.route('/api/recognize_text', methods=['POST'])
def recognize_text():
    data = request.json
    filename = data.get('image_name')
    regions = data.get('regions', None)  # Optional - if not provided, process all regions

    if not filename:
        return jsonify({'status': 'error', 'msg': 'No image name provided'}), 400

    # Initialize progress tracking
    total_regions = len(regions) if regions else len(storage.load_json(filename).get('regions', []))
    recognition_progress[filename] = {'processed': 0, 'total': total_regions, 'status': 'processing'}

        # Async background processing
    def task():
        from logic import recognize_text_with_trocr

        def update_progress(processed, total):
            recognition_progress[filename] = {'processed': processed, 'total': total, 'status': 'processing'}

        recognize_text_with_trocr(filename, regions, progress_callback=update_progress)
        # Mark as complete when done
        recognition_progress[filename] = {'processed': total_regions, 'total': total_regions, 'status': 'completed'}

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

@app.route('/api/recognize_progress/<filename>')
def recognize_progress(filename):
    progress_data = recognition_progress.get(filename, {'processed': 0, 'total': 0, 'status': 'not_started'})
    if progress_data['total'] > 0:
        percentage = int((progress_data['processed'] / progress_data['total']) * 100)
    else:
        percentage = 0

    return jsonify({
        'status': progress_data['status'],
        'processed': progress_data['processed'],
        'total': progress_data['total'],
        'percentage': percentage
    })


# --- Project Management API ---
@app.route('/api/projects', methods=['GET', 'POST'])
def projects():
    if request.method == 'GET':
        projects = storage.get_projects_list()
        return jsonify({'projects': projects})
    elif request.method == 'POST':
        try:
            data = request.json
            print(f"Received project creation request: {data}")  # Debug log
            name = data.get('name')
            description = data.get('description', '')

            if not name:
                print("Project name is missing or empty")  # Debug log
                return jsonify({'status': 'error', 'msg': 'Project name is required'}), 400

            success, result = storage.create_project(name, description)
            print(f"Project creation result: success={success}, result={result}")  # Debug log
            if success:
                return jsonify({'status': 'success', 'project': result})
            else:
                return jsonify({'status': 'error', 'msg': result}), 400
        except Exception as e:
            print(f"Error in project creation endpoint: {e}")  # Debug log
            return jsonify({'status': 'error', 'msg': f'Server error: {str(e)}'}), 500


@app.route('/api/projects/<project_name>', methods=['GET', 'PUT', 'DELETE'])
def project(project_name):
    if request.method == 'GET':
        # Get project details
        projects = storage.get_projects_list()
        project = next((p for p in projects if p['name'] == project_name), None)
        if not project:
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404
        return jsonify({'project': project})

    elif request.method == 'PUT':
        # Update project (for renaming or updating description)
        data = request.json
        new_name = data.get('name')
        description = data.get('description', '')

        # Sanitize both old and new names
        sanitized_old_name = re.sub(r'[<>:"/\\|?*]', '_', project_name)
        old_project_path = os.path.join(storage.PROJECTS_FOLDER, sanitized_old_name)

        # If name is being changed, sanitize the new name too
        if new_name and new_name != project_name:
            sanitized_new_name = re.sub(r'[<>:"/\\|?*]', '_', new_name)
            new_project_path = os.path.join(storage.PROJECTS_FOLDER, sanitized_new_name)

            # Check if new name already exists
            if os.path.exists(new_project_path):
                return jsonify({'status': 'error', 'msg': 'Project with this name already exists'}), 400

            # Rename the project directory
            try:
                os.rename(old_project_path, new_project_path)
                project_name = new_name  # Update the project_name variable to the new name
                sanitized_old_name = sanitized_new_name  # Update the sanitized name
                old_project_path = new_project_path  # Update the path
            except OSError as e:
                return jsonify({'status': 'error', 'msg': f'Failed to rename project: {str(e)}'}), 500

        project_json_path = os.path.join(old_project_path, 'project.json')

        if not os.path.exists(project_json_path):
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404

        with open(project_json_path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)

        # Update name and description
        if new_name:
            project_data['name'] = new_name
        project_data['description'] = description

        with open(project_json_path, 'w', encoding='utf-8') as f:
            json.dump(project_data, f, indent=4, ensure_ascii=False)

        return jsonify({'status': 'success', 'project': project_data})

    elif request.method == 'DELETE':
        success, msg = storage.delete_project(project_name)
        if success:
            return jsonify({'status': 'success', 'msg': msg})
        else:
            return jsonify({'status': 'error', 'msg': msg}), 400


@app.route('/api/projects/<project_name>/images', methods=['GET', 'POST', 'DELETE'])
def project_images(project_name):
    if request.method == 'GET':
        images = storage.get_project_images(project_name)
        # Add status information for each image
        image_list = []
        for img in images:
            # Check if img is a dictionary (has name and status fields) or just a string
            if isinstance(img, dict):
                # If img is already a dictionary with name and status, use it directly
                image_list.append(img)
            else:
                # If img is just a string (filename), get its status
                status = storage.get_image_status(img)
                image_list.append({'name': img, 'status': status})
        return jsonify({'images': image_list})

    elif request.method == 'POST':
        data = request.json
        image_name = data.get('image_name')

        if not image_name:
            return jsonify({'status': 'error', 'msg': 'Image name is required'}), 400

        success, result = storage.add_image_to_project(project_name, image_name)
        if success:
            return jsonify({'status': 'success', 'project': result})
        else:
            return jsonify({'status': 'error', 'msg': result}), 400

    elif request.method == 'DELETE':
        data = request.json
        image_name = data.get('image_name')

        if not image_name:
            return jsonify({'status': 'error', 'msg': 'Image name is required'}), 400

        success, result = storage.remove_image_from_project(project_name, image_name)
        if success:
            return jsonify({'status': 'success', 'project': result})
        else:
            return jsonify({'status': 'error', 'msg': result}), 400


@app.route('/api/projects/<project_name>/status')
def project_status(project_name):
    status = storage.get_project_status(project_name)
    return jsonify({'status': status})


@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get all background tasks"""
    from logic import task_manager
    tasks = task_manager.get_all_tasks()
    return jsonify({'tasks': tasks})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    """Get a specific background task"""
    from logic import task_manager
    task = task_manager.get_task(task_id)
    if task is None:
        return jsonify({'status': 'error', 'msg': 'Task not found'}), 404
    return jsonify({'task': task})


# --- Batch Processing API ---
@app.route('/api/projects/<project_name>/batch_detect', methods=['POST'])
def batch_detect(project_name):
    settings = request.json.get('settings', {})

    # Get all images in the project
    images = storage.get_project_images(project_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Start background processing for the entire project
    def task():
        from logic import run_batch_detection_for_project
        run_batch_detection_for_project(project_name, settings)

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': f'Batch detection started for {len(images)} images'})


@app.route('/api/projects/<project_name>/batch_recognize', methods=['POST'])
def batch_recognize(project_name):
    # Get all images in the project
    images = storage.get_project_images(project_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Start background processing for the entire project
    def task():
        from logic import run_batch_recognition_for_project
        run_batch_recognition_for_project(project_name)

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': f'Batch recognition started for {len(images)} images'})


@app.route('/project/<project_name>')
def project_page(project_name):
    # Get project details
    projects = storage.get_projects_list()
    project = next((p for p in projects if p['name'] == project_name), None)
    if not project:
        return "Project not found", 404

    # Get project images with status
    images_response = project_images(project_name)
    images_data = images_response.get_json()
    project['images'] = images_data['images']

    return render_template('project.html', project=project)


@app.route('/api/projects/<project_name>/upload_images', methods=['POST'])
def upload_project_images(project_name):
    if 'images' not in request.files:
        return jsonify({'status': 'error', 'msg': 'No images provided'}), 400

    files = request.files.getlist('images')
    uploaded_count = 0

    for file in files:
        if file and file.filename:
            # Save the image to the main images folder
            filename = file.filename
            filepath = os.path.join(storage.IMAGE_FOLDER, filename)
            file.save(filepath)

            # Add image to project
            success, result = storage.add_image_to_project(project_name, filename)
            if success:
                uploaded_count += 1

    return jsonify({'status': 'success', 'msg': f'Uploaded {uploaded_count} images to project'})


@app.route('/api/projects/<project_name>/export_zip')
def export_project_zip(project_name):
    import zipfile
    import io
    from flask import send_file
    from PIL import Image
    import xml.etree.ElementTree as ET

    # Get project details
    projects = storage.get_projects_list()
    project = next((p for p in projects if p['name'] == project_name), None)
    if not project:
        return "Project not found", 404

    # Get project images
    images = storage.get_project_images(project_name)

    # Create a zip file in memory
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add images to zip
        for image_item in images:
            # Check if image_item is a dictionary (has name field) or just a string
            image_name = image_item['name'] if isinstance(image_item, dict) else image_item

            image_path = os.path.join(storage.IMAGE_FOLDER, image_name)
            if os.path.exists(image_path):
                # Add image to the root of the archive (not in subfolder)
                zipf.write(image_path, image_name)

                # Create corresponding PAGE XML annotation file
                annotation_name = os.path.splitext(image_name)[0] + '.xml'
                
                # Load annotation data from JSON
                json_annotation_path = os.path.join(storage.ANNOTATION_FOLDER, os.path.splitext(image_name)[0] + '.json')
                annotation_data = {}
                if os.path.exists(json_annotation_path):
                    with open(json_annotation_path, 'r', encoding='utf-8') as f:
                        annotation_data = json.load(f)

                # Create PAGE XML structure
                root = ET.Element('PcGts', xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15")
                page = ET.SubElement(root, 'Page', imageFilename=image_name)
                
                # Get image dimensions
                try:
                    with Image.open(image_path) as img:
                        w, h = img.size
                except:
                    w, h = 0, 0
                
                page.set('imageWidth', str(w))
                page.set('imageHeight', str(h))
                
                # Add text regions and lines
                text_region = ET.SubElement(page, 'TextRegion', id='r1')
                
                regions = annotation_data.get('regions', [])
                for i, reg in enumerate(regions):
                    points = reg.get('points', [])
                    if points:
                        # Format points as required by PAGE XML
                        pts_str = " ".join([f"{p['x']},{p['y']}" for p in points])
                        
                        text_line = ET.SubElement(text_region, 'TextLine', id=f'l{i}')
                        coords = ET.SubElement(text_line, 'Coords', points=pts_str)
                
                # Write XML to archive
                xml_content = ET.tostring(root, encoding='utf-8')
                zipf.writestr(annotation_name, xml_content)

        # Add project metadata
        project_json_path = os.path.join(storage.PROJECTS_FOLDER, project_name, 'project.json')
        if os.path.exists(project_json_path):
            zipf.write(project_json_path, 'project.json')

    memory_file.seek(0)
    return send_file(memory_file, as_attachment=True, download_name=f'{project_name}_export.zip')


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)