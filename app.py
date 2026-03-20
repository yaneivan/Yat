from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, send_file, session
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import argparse
import io
import logging
import os
import threading
import time
import traceback

import logic
import storage
import config

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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Initialize database only if not running tests
import sys
if 'pytest' not in sys.modules:
    init_db()
    logger.info("Database initialized")

# Initialize AI models at startup
if ai_service.is_trocr_available():
    try:
        ai_service.initialize_models("raxtemur/trocr-base-ru")
        logger.info("AI models initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing AI models: {e}", exc_info=True)

app = Flask(__name__)

# =============================================================================
# CSRF Protection
# =============================================================================
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Token doesn't expire
csrf = CSRFProtect(app)

# Whitelist API endpoints from CSRF (they use session-based auth instead)
# CSRF protection is bypassed for API endpoints that are already protected
# by role-based access control and session validation
csrf.exempt('api_blueprint') if 'api_blueprint' in dir() else None

# =============================================================================
# Password Protection with Role-based Access
# =============================================================================
# Set secret key for sessions (required for auth)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this-secret-key-in-production')

# Determine authentication mode
# Two modes only:
# 1. No passwords (both None) → open access, everyone is admin, no login required
# 2. Both passwords set → role-based access (admin/user), login required
USE_AUTH = config.USE_ROLE_BASED_AUTH


def get_user_role():
    """Get current user's role from session."""
    if not USE_AUTH:
        return 'admin'  # Open access mode
    return session.get('role', None)


def is_admin():
    """Check if current user is admin."""
    return get_user_role() == 'admin'


def require_admin(f):
    """Decorator to restrict access to admin users only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if USE_AUTH and not is_admin():
            return jsonify({'error': 'Admin access required'}), 403
        return f(*args, **kwargs)
    return decorated_function


@app.before_request
def check_auth():
    """Check authorization if password protection is enabled."""
    if not USE_AUTH:
        return  # No password - open access, everyone is admin

    # Skip login page, static files, and auth API
    if request.path in ['/login', '/static', '/favicon.ico', '/api/auth/me']:
        return

    # No session - redirect to login
    if 'role' not in session:
        return redirect(url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page for password protection."""
    if not USE_AUTH:
        # No passwords configured - open access, redirect to home
        return redirect('/')

    if request.method == 'POST':
        password = request.form.get('password')
        
        if password == config.ADMIN_PASSWORD:
            session['role'] = 'admin'
            return redirect('/')
        elif password == config.USER_PASSWORD:
            session['role'] = 'user'
            return redirect('/')
        else:
            return render_template('login.html', error='Неверный пароль')
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout - clear session."""
    session.pop('role', None)
    return redirect(url_for('login'))


# Make USE_AUTH and user role available to templates
@app.context_processor
def inject_auth():
    return {
        'USE_AUTH': USE_AUTH,
        'user_role': get_user_role(),
        'is_admin': is_admin()
    }


# =============================================================================

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
    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        return send_from_directory(storage.IMAGE_FOLDER, validated)
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400

@app.route('/data/originals/<path:filename>')
def serve_original(filename):
    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        return send_from_directory(storage.ORIGINALS_FOLDER, validated)
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400
    except Exception:
        # Fallback to images folder only if filename is valid
        try:
            validated = image_service._validate_filename(filename)
            return send_from_directory(storage.IMAGE_FOLDER, validated)
        except ValueError:
            return jsonify({'error': 'Invalid filename'}), 400

# --- API: Annotations ---
@app.route('/api/load/<filename>')
def load_data(filename):
    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        data = annotation_service.get_annotation(validated)
        return jsonify(data)
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400
    except Exception as e:
        return jsonify({'status': 'error', 'msg': str(e)}), 500

@app.route('/api/save', methods=['POST'])
def save_data():
    incoming_data = request.json
    filename = incoming_data.get('image_name')

    if not filename:
        return jsonify({'status': 'error', 'msg': 'No filename'}), 400

    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)

        # Load existing data
        existing_data = annotation_service.get_annotation(validated)

        # Update fields
        for key in ['regions', 'texts', 'status', 'processing_params', 'crop_params']:
            if key in incoming_data:
                existing_data[key] = incoming_data[key]

        # Ensure image_name is set
        existing_data['image_name'] = validated

        logger.info(f"Saving annotation for {validated}: {len(incoming_data.get('regions', []))} regions")

        if annotation_service.save_annotation(validated, existing_data):
            logger.info(f"Save successful")
            return jsonify({'status': 'success'})
        logger.warning(f"Save failed - annotation_service returned False")
        return jsonify({'status': 'error'}), 500

    except ValueError as e:
        logger.error(f"ValueError: {e}")
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400
    except Exception as e:
        logger.error(f"Exception: {e}", exc_info=True)
        return jsonify({'status': 'error', 'msg': str(e)}), 500


# --- API: Crop ---
@app.route('/api/crop', methods=['POST'])
def crop():
    data = request.json
    filename = data.get('image_name')
    box = data.get('box')

    if not filename or not box:
        return jsonify({'status': 'error', 'msg': 'No data'}), 400

    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400

    # Async background processing
    def task():
        image_service.crop_image(validated, box)

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

# --- API: Import/Export ---
@app.route('/api/import_zip', methods=['POST'])
def import_zip_route():
    # Admin only: import ZIP
    if USE_AUTH and not is_admin():
        return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
    
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
        logger.error(f"Import error: {e}", exc_info=True)
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
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        regions = ai_service.detect_lines(validated, settings)
        return jsonify({'status': 'success', 'regions': regions})
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400
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

    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400

    # Get regions count for progress
    if regions is None:
        annotation_data = annotation_service.get_annotation(validated)
        regions = annotation_data.get('regions', [])

    total_regions = len(regions)
    recognition_progress[validated] = {'processed': 0, 'total': total_regions, 'status': 'processing'}

    # Async background processing
    def task():
        def update_progress(processed, total):
            recognition_progress[validated] = {
                'processed': processed,
                'total': total,
                'status': 'processing'
            }

        try:
            ai_service.recognize_text(validated, regions, progress_callback=update_progress)
            recognition_progress[validated] = {
                'processed': total_regions,
                'total': total_regions,
                'status': 'completed'
            }
        except Exception as e:
            # При ошибке тоже очищаем запись
            recognition_progress[validated] = {
                'processed': 0,
                'total': total_regions,
                'status': 'failed',
                'error': str(e)
            }
        finally:
            # 🔧 Очистка записи после завершения (предотвращает утечку памяти)
            # Даём клиенту время (5 секунд) прочитать финальный статус перед удалением
            time.sleep(5)
            if validated in recognition_progress:
                del recognition_progress[validated]

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

@app.route('/api/recognize_progress/<filename>')
def recognize_progress(filename):
    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400
    
    progress_data = recognition_progress.get(
        validated,
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
        # Admin only: create project
        if USE_AUTH and not is_admin():
            return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
        
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
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    if request.method == 'GET':
        project_data = project_service.get_project(sanitized_name)

        if not project_data:
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404

        return jsonify({'project': project_data})

    elif request.method == 'PUT':
        # Admin only: edit project
        if USE_AUTH and not is_admin():
            return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
        
        data = request.json
        new_name = data.get('name')
        description = data.get('description')

        result = project_service.update_project(
            sanitized_name,
            new_name=new_name,
            description=description
        )

        if result:
            return jsonify({'status': 'success', 'project': result})
        else:
            return jsonify({'status': 'error', 'msg': 'Project not found or name collision'}), 400

    elif request.method == 'DELETE':
        # Admin only: delete project
        if USE_AUTH and not is_admin():
            return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
        
        result = project_service.delete_project(sanitized_name)

        if result:
            return jsonify({'status': 'success', 'msg': 'Project deleted'})
        else:
            return jsonify({'status': 'error', 'msg': 'Project not found'}), 404


@app.route('/api/projects/<project_name>/images', methods=['GET', 'DELETE'])
def project_images(project_name):
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    if request.method == 'GET':
        images = project_service.get_images(sanitized_name)
        return jsonify({'images': images})

    elif request.method == 'DELETE':
        # Admin only: remove image from project
        if USE_AUTH and not is_admin():
            return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
        
        data = request.json
        image_name = data.get('image_name')

        if not image_name:
            return jsonify({'status': 'error', 'msg': 'Image name is required'}), 400

        result = project_service.remove_image(sanitized_name, image_name)

        if result:
            return jsonify({'status': 'success', 'msg': 'Image removed from project'})
        else:
            return jsonify({'status': 'error', 'msg': 'Image or project not found'}), 404


@app.route('/api/projects/<project_name>/upload_images', methods=['POST'])
def upload_project_images(project_name):
    # Admin only: upload images
    if USE_AUTH and not is_admin():
        return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
    
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

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
            filename = image_service.upload_image(file, project_name=sanitized_name)
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
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    zip_data = project_service.export_to_zip(sanitized_name)

    if zip_data is None:
        return jsonify({'status': 'error', 'msg': 'Project not found'}), 404

    return send_file(
        io.BytesIO(zip_data),
        as_attachment=True,
        download_name=f'{sanitized_name}_export.zip',
        mimetype='application/zip'
    )


@app.route('/api/projects/<project_name>/export_pdf')
def export_project_pdf(project_name):
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)
    
    # Get variant from query parameter (default: overlay)
    variant = request.args.get('variant', 'overlay')
    
    # Validate variant
    valid_variants = ['original', 'overlay', 'parallel', 'text']
    if variant not in valid_variants:
        return jsonify({'status': 'error', 'msg': f'Invalid variant. Must be one of: {valid_variants}'}), 400
    
    # Import PDF export service
    from services.pdf_export_service import pdf_export_service
    
    # Generate PDF
    pdf_data = pdf_export_service.export_project(sanitized_name, variant=variant)
    
    if pdf_data is None:
        return jsonify({'status': 'error', 'msg': 'Project not found or export failed'}), 404
    
    # Determine filename
    variant_names = {
        'original': 'images_only',
        'overlay': 'with_text_overlay',
        'parallel': 'side_by_side',
        'text': 'text_only'
    }
    
    return send_file(
        io.BytesIO(pdf_data),
        as_attachment=True,
        download_name=f'{sanitized_name}_{variant_names[variant]}.pdf',
        mimetype='application/pdf'
    )


@app.route('/api/projects/<project_name>/batch_detect', methods=['POST'])
def batch_detect(project_name):
    # Admin only: batch detection
    if USE_AUTH and not is_admin():
        return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
    
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    settings = request.json.get('settings', {})
    images = project_service.get_images(sanitized_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Get project for project_id
    project = project_service.get_project(sanitized_name)
    project_id = None
    if project:
        # Get project_id from DB
        from database.session import SessionLocal
        from database.repository.project_repository import ProjectRepository
        session = SessionLocal()
        try:
            repo = ProjectRepository(session)
            db_project = repo.get_by_name(sanitized_name)
            if db_project:
                project_id = db_project.id
        finally:
            session.close()

    # Create task and run in background
    task = task_service.create_task(
        task_type="batch_detection",
        project_name=sanitized_name,
        project_id=project_id,
        images=[img['filename'] if isinstance(img, dict) else img for img in images],
        description=f"Batch detection for project {sanitized_name}"
    )

    task_service.run_background(
        task=task,
        func=logic.run_batch_detection_for_project,
        project_name=sanitized_name,
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
    # Admin only: batch recognition
    if USE_AUTH and not is_admin():
        return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403
    
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    images = project_service.get_images(sanitized_name)

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Get project_id
    from database.session import SessionLocal
    from database.repository.project_repository import ProjectRepository
    session = SessionLocal()
    project_id = None
    try:
        repo = ProjectRepository(session)
        db_project = repo.get_by_name(sanitized_name)
        if db_project:
            project_id = db_project.id
    finally:
        session.close()

    # Create task and run in background
    task = task_service.create_task(
        task_type="batch_recognition",
        project_name=sanitized_name,
        project_id=project_id,
        images=[img['filename'] if isinstance(img, dict) else img for img in images],
        description=f"Batch recognition for project {sanitized_name}"
    )

    task_service.run_background(
        task=task,
        func=logic.run_batch_recognition_for_project,
        project_name=sanitized_name,
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


# --- API: Auth ---
@app.route('/api/auth/me', methods=['GET'])
def get_current_user():
    """Get current user's role."""
    if not USE_AUTH:
        return jsonify({'role': 'admin', 'is_admin': True})
    role = get_user_role()
    return jsonify({'role': role or 'none', 'is_admin': is_admin()})


# --- Pages: Project ---
@app.route('/project/<project_name>')
def project_page(project_name):
    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)
    
    project_data = project_service.get_project(sanitized_name)

    if not project_data:
        return "Project not found", 404

    images = project_service.get_images(sanitized_name)
    project_data['images'] = images

    return render_template('project.html', project=project_data)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
