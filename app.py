from flask import Flask, render_template, request, jsonify, redirect, url_for, send_from_directory, send_file, session, abort
from flask_wtf.csrf import CSRFProtect
from functools import wraps
import io
import logging
import os
import threading
import time

import logic
import config

# Import services
from services import (
    task_service,
    annotation_service,
    image_service,
    project_service,
    ai_service,
    image_storage_service,
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
# CSRF can be enabled/disabled via .env file
# For development over HTTP (external IP), set CSRF_ENABLED=false in .env
# For production (HTTPS or localhost), set CSRF_ENABLED=true in .env
CSRF_ENABLED = os.environ.get('CSRF_ENABLED', 'true').lower() == 'true'

if CSRF_ENABLED:
    app.config['WTF_CSRF_ENABLED'] = True
    app.config['WTF_CSRF_TIME_LIMIT'] = None
    app.config['WTF_CSRF_SSL_STRICT'] = False  # Allow non-HTTPS for development
    app.config['WTF_CSRF_HEADERS'] = ['X-CSRFToken', 'X-Requested-With', 'X-Csrf-Token']
    csrf = CSRFProtect(app)
    logger.info("CSRF protection ENABLED")
else:
    app.config['WTF_CSRF_ENABLED'] = False
    csrf = CSRFProtect(app)  # Keep reference but disabled
    logger.info("CSRF protection DISABLED")

# =============================================================================
# Password Protection with Role-based Access
# =============================================================================
# Set secret key for sessions (required for auth)
# IMPORTANT: Use a fixed secret key in production to persist sessions across restarts
app.secret_key = os.environ.get('SECRET_KEY', 'yat-htr-annotation-tool-secret-key-2026')

# Session cookie settings for development (HTTP)
# In production with HTTPS, set SESSION_COOKIE_SECURE = True
app.config['SESSION_COOKIE_SECURE'] = False  # Allow HTTP
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Allow cross-site for navigation

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
    if request.path in ['/login', '/favicon.ico', '/api/auth/me'] or request.path.startswith('/static/'):
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

# Make csrf_token available even when CSRF is disabled
@app.context_processor
def inject_csrf():
    def csrf_token():
        if CSRF_ENABLED:
            from flask_wtf.csrf import generate_csrf
            return generate_csrf()
        return ''
    return {'csrf_token': csrf_token}


# =============================================================================

# --- Pages ---
@app.route('/')
def index():
    images = image_service.get_all_images()
    return render_template('index.html', files=images)

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
    # Проверка существования файла
    if not image_service.get_original_path(filename, project_name):
        abort(404)
    return render_template('cropper.html', filename=filename, project=project_name)

# --- API: Images ---
@app.route('/api/images_list')
def list_images():
    project = request.args.get('project')
    if project:
        images = image_service.get_all_images(project_name=project)
    else:
        images = image_service.get_all_images()
    return jsonify(images)

@app.route('/api/image_url')
def image_url():
    """Get URL for an image, optionally scoped to a project."""
    filename = request.args.get('filename')
    project = request.args.get('project')
    image_type = request.args.get('type', 'image')  # 'image' or 'original'
    cache_bust = request.args.get('t')

    if not filename:
        return jsonify({'error': 'No filename provided'}), 400

    try:
        if image_type == 'original':
            url = image_storage_service.get_original_url(filename, project, cache_bust)
        else:
            url = image_storage_service.get_image_url(filename, project, cache_bust)
        return jsonify({'url': url})
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/data/images/<path:filename>')
def serve_image(filename):
    try:
        validated = image_storage_service._validate_filename(filename)
        project_name = request.args.get('project')
        file_path = image_storage_service.get_image_path(validated, project_name)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Image not found'}), 404
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400

@app.route('/data/originals/<path:filename>')
def serve_original(filename):
    try:
        validated = image_storage_service._validate_filename(filename)
        project_name = request.args.get('project')
        file_path = image_storage_service.get_original_path(validated, project_name)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Original not found'}), 404
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400

@app.route('/data/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    try:
        validated = image_storage_service._validate_filename(filename)
        project_name = request.args.get('project')

        # filename приходит как "ProjectName/name_thumb.jpg" или "name_thumb.jpg"
        # Нужно извлечь оригинальное имя файла
        thumb_basename = os.path.basename(validated)
        # Убрать "_thumb.jpg" чтобы получить оригинальное имя
        if thumb_basename.endswith('_thumb.jpg'):
            original_name = thumb_basename[:-10]  # убрать "_thumb.jpg"
        else:
            original_name = thumb_basename

        file_path = image_storage_service.get_thumbnail_path(original_name, project_name)

        if not os.path.exists(file_path):
            # Fallback: сгенерировать на лету
            for ext in ['.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp']:
                if image_storage_service.image_exists(original_name + ext, project_name):
                    image_storage_service.generate_thumbnail(original_name + ext, project_name)
                    break

            if not os.path.exists(file_path):
                return jsonify({'error': 'Thumbnail not found'}), 404
        return send_from_directory(os.path.dirname(file_path), os.path.basename(file_path))
    except ValueError:
        return jsonify({'error': 'Invalid filename'}), 400

# --- API: Annotations ---
@app.route('/api/load/<filename>')
def load_data(filename):
    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        # Get project from query parameter
        project_name = request.args.get('project')
        data = annotation_service.get_annotation(validated, project_name)
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
        
        # Get project from query parameter
        project_name = request.args.get('project')

        # Load existing data with project scope
        existing_data = annotation_service.get_annotation(validated, project_name)

        # Update fields
        for key in ['regions', 'texts', 'status', 'processing_params', 'crop_params']:
            if key in incoming_data:
                existing_data[key] = incoming_data[key]

        # Ensure image_name is set
        existing_data['image_name'] = validated

        logger.info(f"Saving annotation for {validated}: {len(incoming_data.get('regions', []))} regions")

        if annotation_service.save_annotation(validated, existing_data, project_name):
            logger.info("Save successful")
            return jsonify({'status': 'success'})
        logger.warning("Save failed - annotation_service returned False")
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
        
        # Get project from query parameter
        project_name = request.args.get('project')
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400

    # Async background processing
    def task():
        image_service.crop_image(validated, box, project_name)

    thread = threading.Thread(target=task)
    thread.start()

    return jsonify({'status': 'success', 'msg': 'Background processing started'})

# --- API: Import/Export ---
@app.route('/api/import_zip', methods=['POST'])
def import_zip_route():
    # Admin only: import ZIP
    if USE_AUTH and not is_admin():
        logger.warning(f"[ZIP Import] Access denied: user={get_current_user() if USE_AUTH else 'anonymous'}")
        return jsonify({'status': 'error', 'msg': 'Admin access required'}), 403

    try:
        logger.info("[ZIP Import] Request received")
        logger.debug(f"[ZIP Import] Form keys: {list(request.form.keys())}")
        logger.debug(f"[ZIP Import] Files keys: {list(request.files.keys())}")
        
        simp = int(request.form.get('simplify', 0))
        project_name = request.form.get('project_name', None)
        logger.info(f"[ZIP Import] simplify={simp}, project_name={project_name}")

        if 'file' not in request.files:
            logger.error(f"[ZIP Import] No file in request. Available files: {list(request.files.keys())}")
            return jsonify({'status': 'error', 'msg': 'No file in request'}), 400

        uploaded_file = request.files['file']
        if uploaded_file.filename == '':
            logger.error("[ZIP Import] No file selected")
            return jsonify({'status': 'error', 'msg': 'No file selected'}), 400

        logger.info(f"[ZIP Import] File: {uploaded_file.filename}, size: {uploaded_file.content_length}")

        # Use logic function for import (keeps existing ZIP processing)
        count, final_project_name = logic.process_zip_import(uploaded_file, simp, project_name)
        logger.info(f"[ZIP Import] Success: {count} images imported to '{final_project_name}'")
        return jsonify({
            'status': 'success',
            'count': count,
            'project_name': final_project_name
        })

    except Exception as e:
        logger.error(f"[ZIP Import] Error: {e}", exc_info=True)
        return jsonify({'status': 'error', 'msg': str(e)}), 500

# --- API: AI Operations ---
@app.route('/api/detect_lines', methods=['POST'])
def detect_lines():
    data = request.json
    filename = data.get('image_name')
    settings = data.get('settings', {})
    project_name = request.args.get('project')

    if not filename:
        return jsonify({'status': 'error', 'msg': 'No image name provided'}), 400

    try:
        # Validate filename to prevent path traversal
        validated = image_service._validate_filename(filename)
        regions = ai_service.detect_lines(validated, settings, project_name)
        return jsonify({'status': 'success', 'regions': regions})
    except ValueError:
        logger.error(f"detect_lines: Invalid filename - {filename}")
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400
    except Exception as e:
        logger.error(f"detect_lines error: {e}", exc_info=True)
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
        
        # Get project from request data
        project_name = data.get('project')
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400

    # Get regions count for progress
    if regions is None:
        annotation_data = annotation_service.get_annotation(validated, project_name)
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
            ai_service.recognize_text(validated, regions, progress_callback=update_progress, project_name=project_name)
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


@app.route('/api/projects/<project_name>/images/<filename>/status', methods=['GET', 'PUT'])
def image_status(project_name, filename):
    """Get or update image status and comment."""
    # Sanitize project name and filename
    sanitized_name = project_service._sanitize_name(project_name)
    
    try:
        validated_filename = image_service._validate_filename(filename)
    except ValueError:
        return jsonify({'status': 'error', 'msg': 'Invalid filename'}), 400

    if request.method == 'GET':
        # Get image status
        result = image_service.get_status(validated_filename, sanitized_name)
        if not result:
            return jsonify({'status': 'error', 'msg': 'Image not found'}), 404
        
        return jsonify(result)

    elif request.method == 'PUT':
        # Update status and/or comment
        data = request.json
        new_status = data.get('status')
        new_comment = data.get('comment')
        
        success = image_service.update_status(
            validated_filename,
            sanitized_name,
            status=new_status,
            comment=new_comment
        )
        
        if not success:
            return jsonify({'status': 'error', 'msg': 'Image not found'}), 404
        
        # Return updated status
        updated = image_service.get_status(validated_filename, sanitized_name)
        return jsonify({
            'status': 'success',
            'message': 'Status updated',
            **updated
        })


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

    logger.info(f"POST /api/projects/{project_name}/batch_detect")

    # Sanitize project name to prevent path traversal
    sanitized_name = project_service._sanitize_name(project_name)

    settings = request.json.get('settings', {})
    selected_images = request.json.get('images', [])  # Empty list = all images
    
    logger.info(f"  selected_images: {len(selected_images)} images")
    
    # Get all images from project
    all_images = project_service.get_images(sanitized_name)

    if not all_images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Filter images if specific ones were selected
    if selected_images:
        images = [img for img in all_images if (img['filename'] if isinstance(img, dict) else img) in selected_images]
    else:
        images = all_images

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images selected'}), 400

    logger.info(f"  processing {len(images)} images")

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
                logger.info(f"  project_id: {project_id}")
        finally:
            session.close()

    # Create task and run in background
    task = task_service.create_task(
        task_type="batch_detection",
        project_name=sanitized_name,
        project_id=project_id,
        images=[img['filename'] if isinstance(img, dict) else img for img in images],
        description=f"Batch detection for {len(images)} images"
    )

    logger.info(f"  created task {task.id}")

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

    selected_images = request.json.get('images', [])  # Empty list = all images
    
    # Get all images from project
    all_images = project_service.get_images(sanitized_name)

    if not all_images:
        return jsonify({'status': 'error', 'msg': 'No images in project'}), 400

    # Filter images if specific ones were selected
    if selected_images:
        images = [img for img in all_images if (img['filename'] if isinstance(img, dict) else img) in selected_images]
    else:
        images = all_images

    if not images:
        return jsonify({'status': 'error', 'msg': 'No images selected'}), 400

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
        description=f"Batch recognition for {len(images)} images"
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
    logger.info(f"GET /api/tasks: returning {len(tasks)} tasks")
    for task in tasks:
        logger.info(f"  Task {task.id}: type={task.type}, project={task.project_name}, status={task.status}")
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
        abort(404)

    images = project_service.get_images(sanitized_name)
    project_data['images'] = images

    return render_template('project.html', project=project_data)


# --- Error Handlers ---
@app.errorhandler(404)
def handle_404(error):
    """Обработчик 404 ошибки."""
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000, use_reloader=True)
