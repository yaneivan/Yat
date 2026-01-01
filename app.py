from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for, send_file
import storage
import logic
import threading

app = Flask(__name__)

# --- Pages ---
@app.route('/')
def index():
    return render_template('index.html', files=storage.get_images_with_status())

@app.route('/editor')
def editor():
    filename = request.args.get('image')
    if not filename: return redirect(url_for('index'))
    return render_template('editor.html', filename=filename)

@app.route('/cropper')
def cropper():
    filename = request.args.get('image')
    if not filename: return redirect(url_for('index'))
    return render_template('cropper.html', filename=filename)

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
    if storage.save_json(request.json): return jsonify({'status': 'success'})
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
        simp = int(request.form.get('simplify', 0))
    except: simp = 0
    count = logic.process_zip_import(request.files['file'], simp)
    return jsonify({'status': 'success', 'count': count})

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

if __name__ == '__main__':
    app.run(debug=True, port=5000)