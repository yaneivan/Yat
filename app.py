from flask import Flask, render_template, request, jsonify, send_from_directory, redirect, url_for
import utils

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html', files=utils.get_sorted_images())

@app.route('/editor')
def editor():
    filename = request.args.get('image')
    if not filename: return redirect(url_for('index'))
    return render_template('editor.html', filename=filename)

# --- API ---

@app.route('/api/images_list')
def api_images_list():
    return jsonify(utils.get_sorted_images())

@app.route('/data/images/<path:filename>')
def serve_image(filename):
    return send_from_directory(utils.IMAGE_FOLDER, filename)

@app.route('/api/upload', methods=['POST'])
def upload_files():
    files = request.files.getlist('files[]')
    count = 0
    for f in files:
        if utils.save_image(f): count += 1
    return jsonify({'status': 'success', 'count': count})

@app.route('/api/import_zip', methods=['POST'])
def import_zip():
    if 'file' not in request.files: return jsonify({'status': 'error'})
    count = utils.process_zip_import(request.files['file'])
    return jsonify({'status': 'success', 'count': count})

@app.route('/api/delete', methods=['POST'])
def delete_files():
    count = utils.delete_files(request.json.get('filenames', []))
    return jsonify({'status': 'success', 'deleted': count})

@app.route('/api/save', methods=['POST'])
def save_annotation():
    if utils.save_annotation(request.json):
        return jsonify({'status': 'success'})
    return jsonify({'status': 'error'}), 400

@app.route('/api/load/<filename>')
def load_annotation(filename):
    return jsonify(utils.load_annotation(filename))

if __name__ == '__main__':
    app.run(debug=True, port=5000)