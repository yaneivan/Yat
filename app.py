from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, send_file
import io
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime

import config
import logic
import storage

# Import services
from services import (
    task_service,
    annotation_service,
    image_service,
    project_service,
    ai_service,
)

# Import database
from database.session import init_db

# Initialize database only if not running tests
import sys
if 'pytest' not in sys.modules:
    init_db()
    print("Database initialized")

# Initialize AI models at startup
if ai_service.is_trocr_available():
    try:
        ai_service.initialize_models("raxtemur/trocr-base-ru")
        print("AI models initialized successfully")
    except Exception as e:
        print(f"Error initializing AI models: {e}")

app = Flask(__name__)

# --- Pages ---
@app.route('/')
def index():
    return render_template('index.html', files=storage.get_images_with_status())

@app.route('/editor')
def editor():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename:
        return redirect(url_for('index'))
    return render_template('editor.html', filename=filename, project=project_name)

@app.route('/text_editor')
def text_editor():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename:
        return redirect(url_for('index'))
    return render_template('text_editor.html', filename=filename, project=project_name)

@app.route('/cropper')
def cropper():
    filename = request.args.get('image')
    project_name = request.args.get('project')
    if not filename:
        return redirect(url_for('index'))
    return render_template('cropper.html', filename=filename, project=project_name)

# --- API: Images ---
@app.route('/api/images_list')
def list_images():
    images = image_service.get_all_images()
    return jsonify([img['name'] for img in images])

@app.route('/data/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(storage.IMAGE_FOLDER, filename)

@app.route('/data/originals/<path:filename>')
def serve_original(filename):
    try:
        return send_from_directory(storage.ORIGINALS_FOLDER, filename)
    except:
        return send_from_directory(storage.IMAGE_FOLDER, filename)

# --- API: Annotations ---
@app.route('/api/load/<filename>')
def load_data(filename):
    try:
        data = annotation_service.get_annotation(filename)
        return jsonify(data)
    except ValueError as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_data():
    incoming_data = request.json
    filename = incoming_data.get('image_name')
    
    if not filename:
        return jsonify({'status': 'error', 'msg': 'No filename'}), 400

    try:
        # Load existing data
        existing_data = annotation_service.get_annotation(filename)

        # Update fields
        for key in ['regions', 'texts', 'status', 'processing_params', 'crop_params']:
            if key in incoming_data:
                existing_data[key] = incoming_data[key]

        # Ensure image_name is set
        existing_data['image_name'] = filename

        if annotation_service.save_annotation(filename, existing_data):
            return jsonify({'status': 'success'})
        return jsonify({'status': 'error'}), 500
        
    except ValueError as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# --- API: Crop ---
@app.route('/api/crop', methods=['POST'])
def crop():
    data = request.json
    filename = data.get('image_name')
    box = data.get('box')

    if not filename or not box:
        return jsonify({'status': 'error', 'msg': 'No data'}), 400

    # Async background processing
    def task():
        image_service.crop_image(filename, box)

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

# --- API: Import/Export ---
@app.route('/api/import_zip', methods=['POST'])
def import_zip_route():
    try:
        simp = int(request.form.get('simplify', 0))
        project_name = request.form.get('project_name', None)

        if 'file' not in request.files:
            return jsonify({'status': 'error', 'msg': 'No file in request'}), 400

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            return jsonify({'status': 'error', 'msg': 'No file selected'}), 400

        # Use logic function for import (keeps existing ZIP processing)
        count, final_project_name = logic.process_zip_import(uploaded_file, simp, project_name)
        return jsonify({
            'status': 'success',
            'count': count,
            'project_name': final_project_name
        })

    except Exception as e:
        import traceback
        print(f"Import error: {e}")
        print(traceback.format_exc())
        return jsonify({'status': 'error', 'msg': str(e)}), 500

# --- API: AI Operations ---
@app.route('/api/detect_lines', methods=['POST'])
def detect_lines():
    data = request.json
    filename = data.get('image_name')
    settings = data.get('settings', {})
    
    if not filename:
        return jsonify({'status': 'error', 'msg': 'No image name provided'}), 400

    try:
        regions = ai_service.detect_lines(filename, settings)
        return jsonify({'status': 'success', 'regions': regions})
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

# Global dict for recognition progress (kept for backward compatibility)
recognition_progress = {}

@app.route('/api/recognize_text', methods=['POST'])
def recognize_text():
    data = request.json
    filename = data.get('image_name')
    regions = data.get('regions', None)

    if not filename:
        return jsonify({'status': 'error', 'msg': 'No image name provided'}), 400

    # Get regions count for progress
    if regions is None:
        annotation_data = annotation_service.get_annotation(filename)
        regions = annotation_data.get('regions', [])

    total_regions = len(regions)
    recognition_progress[filename] = {'processed': 0, 'total': total_regions, 'status': 'processing'}

    # Async background processing
    def task():
        def update_progress(processed, total):
            recognition_progress[filename] = {
                'processed': processed,
                'total': total,
                'status': 'processing'
            }

        try:
            ai_service.recognize_text(filename, regions, progress_callback=update_progress)
            recognition_progress[filename] = {
                'processed': total_regions,
                'total': total_regions,
                'status': 'completed'
            }
        except Exception as e:
            # При ошибке тоже очищаем запись
            recognition_progress[filename] = {
                'processed': 0,
                'total': total_regions,
                'status': 'failed',
                'error': str(e)
            }
        finally:
            # 🔧 Очистка записи после завершения (предотвращает утечку памяти)
            # Даём клиенту время (5 секунд) прочитать финальный статус перед удалением
            time.sleep(5)
            if filename in recognition_progress:
                del recognition_progress[filename]

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

@app.route('/api/recognize_progress/<filename>')
def recognize_progress(filename):
    progress_data = recognition_progress.get(
        filename,
        {'processed': 0, 'total': 0, 'status': 'not_started'}
    )
    
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

# --- API: Projects ---
@app.route('/api/projects', methods=['GET', 'POST'])
def projects():
    if request.method == 'GET':
        projects_list = project_service.get_all_projects()
        return jsonify({'projects': projects_list})

    elif request.method == 'POST':
        try:
            data = request.json
            name = data.get('name')
            description = data.get('description', '')

            if not name:
                return jsonify({'status': 'error', 'msg': 'Project name is required'}), 400

            result = project_service.create_project(name, description)

            if result:
                return jsonify({'status': 'success', 'project': result})
            else:
                return jsonify({'status': 'error', 'msg': 'Project already exists'}), 400

        except Exception as e:
            return jsonify({'status': 'error', 'msg': f'Server error: {str(e)}'}), 500


@app.route('/api/projects/<project_name>', methods=['GET', 'PUT', 'DELETE'])
def project(project_name):
    if request.method == 'GET':
        project_data = project_service.get_project(project_name)

        if not project_data:
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404

        return jsonify({'project': project_data})

    elif request.method == 'PUT':
        data = request.json
        new_name = data.get('name')
        description = data.get('description')

        result = project_service.update_project(
            project_name,
            new_name=new_name,
            description=description
        )

        if result:
            return jsonify({'status': 'success', 'project': result})
        else:
            return jsonify({'status': 'error', 'msg': 'Project not found or name collision'}), 400

    elif request.method == 'DELETE':
        result = project_service.delete_project(project_name)

        if result:
            return jsonify({'status': 'success', 'msg': 'Project deleted'})
        else:
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404


@app.route('/api/projects/<project_name>/images', methods=['GET', 'DELETE'])
def project_images(project_name):
    if request.method == 'GET':
        images = project_service.get_images(project_name)
        return jsonify({'images': images})

    elif request.method == 'DELETE':
        data = request.json
        image_name = data.get('image_name')

        if not image_name:
            return jsonify({'status': 'error', 'msg': 'Image name is required'}), 400

        result = project_service.remove_image(project_name, image_name)

        if result:
            return jsonify({'status': 'success', 'msg': 'Image removed from project'})
        else:
            return jsonify({'status': 'error', 'msg': 'Image or project not found'}), 404


@app.route('/api/projects/<project_name>/upload_images', methods=['POST'])
def upload_project_images(project_name):
    if 'images' not in request.files:
        return jsonify({'status': 'error', 'msg': 'No images provided'}), 400

    files = request.files.getlist('images')
    uploaded_count = 0
    skipped_count = 0

    for file in files:
        if file and file.filename:
            # Validate extension
            if not image_service.is_allowed_extension(file.filename):
                continue

            # Save image and add to project
            filename = image_service.upload_image(file, project_name=project_name)
            if filename:
                uploaded_count += 1
            else:
                skipped_count += 1  # Duplicate or invalid

    if uploaded_count == 0 and skipped_count > 0:
        return jsonify({
            'status': 'error',
            'msg': 'Все файлы уже существуют в проекте (дубликаты)'
        }), 409

    return jsonify({
        'status': 'success',
        'msg': f'Загружено {uploaded_count} изображений' + (f' ({skipped_count} пропущено)' if skipped_count > 0 else '')
    })


@app.route('/api/projects/<project_name>/export_zip')
def export_project_zip(project_name):
    zip_data = project_service.export_to_zip(project_name)
    
    if zip_data is None:
        return jsonify({'status': 'error', 'msg': 'Project not found'}), 404
    
    return send_file(
        io.BytesIO(zip_data),
        as_attachment=True,
        download_name=f'{project_name}_export.zip',
        mimetype='application/zip'
    )


@app.route('/api/projects/<project_name>/batch_detect', methods=['POST'])
def batch_detect(project_name):
    settings = request.json.get('settings', {})
    images = project_service.get_images(project_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Get project for project_id
    project = project_service.get_project(project_name)
    project_id = None
    if project:
        # Get project_id from DB
        from database.session import SessionLocal
        from database.repository.project_repository import ProjectRepository
        session = SessionLocal()
        try:
            repo = ProjectRepository(session)
            db_project = repo.get_by_name(project_name)
            if db_project:
                project_id = db_project.id
        finally:
            session.close()

    # Create task and run in background
    task = task_service.create_task(
        task_type="batch_detection",
        project_name=project_name,
        project_id=project_id,
        images=[img['filename'] if isinstance(img, dict) else img for img in images],
        description=f"Batch detection for project {project_name}"
    )

    task_service.run_background(
        task=task,
        func=logic.run_batch_detection_for_project,
        project_name=project_name,
        settings=settings,
        task_id=task.id
    )

    return jsonify({
        'status': 'success',
        'msg': f'Batch detection started for {len(images)} images',
        'task_id': task.id
    })


@app.route('/api/projects/<project_name>/batch_recognize', methods=['POST'])
def batch_recognize(project_name):
    images = project_service.get_images(project_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Get project_id
    from database.session import SessionLocal
    from database.repository.project_repository import ProjectRepository
    session = SessionLocal()
    project_id = None
    try:
        repo = ProjectRepository(session)
        db_project = repo.get_by_name(project_name)
        if db_project:
            project_id = db_project.id
    finally:
        session.close()

    # Create task and run in background
    task = task_service.create_task(
        task_type="batch_recognition",
        project_name=project_name,
        project_id=project_id,
        images=[img['filename'] if isinstance(img, dict) else img for img in images],
        description=f"Batch recognition for project {project_name}"
    )

    task_service.run_background(
        task=task,
        func=logic.run_batch_recognition_for_project,
        project_name=project_name,
        task_id=task.id
    )

    return jsonify({
        'status': 'success',
        'msg': f'Batch recognition started for {len(images)} images',
        'task_id': task.id
    })


# --- API: Tasks ---
@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    tasks = task_service.get_all_tasks()
    return jsonify({'tasks': [t.to_dict() for t in tasks]})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task(task_id):
    task = task_service.get_task(task_id)
    
    if task is None:
        return jsonify({'status': 'error', 'msg': 'Task not found'}), 404
    
    return jsonify({'task': task.to_dict()})


# --- Pages: Project ---
@app.route('/project/<project_name>')
def project_page(project_name):
    project_data = project_service.get_project(project_name)

    if not project_data:
        return "Project not found", 404

    images = project_service.get_images(project_name)
    project_data['images'] = images

    return render_template('project.html', project=project_data)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
