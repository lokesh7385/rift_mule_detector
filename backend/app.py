import os
import uuid
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from graph_engine import analyze

app = Flask(__name__, static_folder='static', static_url_path='')
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500 MB max for large datasets

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

TASKS = {}
TASK_lock = threading.Lock()

def count_lines_approx(filepath):
    """Count lines in file efficiently."""
    try:
        with open(filepath, 'rb') as f:
            # Simple buffer read could be implemented for extreme speed, 
            # but line iteration is acceptable for <1GB in Python 3.
            return sum(1 for _ in f) - 1 # Minus header
    except:
        return 0

def run_full_analysis(file_id, filepath):
    """Background task to run full analysis."""
    try:
        # Full analysis (no limit)
        # Note: We open file again.
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            result = analyze(f, limit=None)
        
        with TASK_lock:
            TASKS[file_id] = {'status': 'done', 'result': result}
    except Exception as e:
        with TASK_lock:
            TASKS[file_id] = {'status': 'error', 'error': str(e)}

@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Handle standard file upload (legacy/fallback)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files are accepted'}), 400

    # Save file
    file_id = str(uuid.uuid4())
    filename = f"{file_id}.csv"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    LIMIT = 15000 
    try:
        # Initialize Background Task Status
        with TASK_lock:
             TASKS[file_id] = {'status': 'uploading'}

        # Run partial analysis
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            partial_result = analyze(f, limit=LIMIT)
        
        # Determine if partial
        # We can count lines or trust analyze partial flag (if we set it)
        # analyze() sets is_partial if rows >= limit
        
        partial_result['file_id'] = file_id
        # We don't know total rows easily without counting, but analyze result has is_partial
        is_partial = partial_result['summary']['is_partial']
        
        if is_partial:
             with TASK_lock:
                TASKS[file_id] = {'status': 'processing'}
             thread = threading.Thread(target=run_full_analysis, args=(file_id, filepath))
             thread.start()
        else:
             with TASK_lock:
                TASKS[file_id] = {'status': 'done', 'result': partial_result} # Or done?

        return jsonify(partial_result)

    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/upload_chunk', methods=['POST'])
def upload_chunk():
    """Handle chunked file upload."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    chunk_index = int(request.form.get('chunkIndex', 0))
    total_chunks = int(request.form.get('totalChunks', 1))
    file_id = request.form.get('fileId')

    if not file_id:
        file_id = str(uuid.uuid4())

    filename = f"{file_id}.csv"
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    try:
        # Write chunk
        mode = 'ab' if chunk_index > 0 else 'wb'
        with open(filepath, mode) as f:
            f.write(file.read())

        response_data = {'file_id': file_id, 'status': 'chunk_received'}

        # First Chunk: Run Partial Analysis immediately
        if chunk_index == 0:
            LIMIT = 15000
            
            # Initialize Background Task Status
            with TASK_lock:
                 TASKS[file_id] = {'status': 'uploading'}

            # Read just written chunk to analyze
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                partial_result = analyze(f, limit=LIMIT)
            
            partial_result['file_id'] = file_id
            partial_result['summary']['total_rows_estimated'] = LIMIT # Placeholder until done
            partial_result['is_partial'] = True 
            # Note: total_rows_estimated unknown yet, but we know it's partial if total_chunks > 1
            if total_chunks == 1:
                partial_result['is_partial'] = False
            
            response_data = partial_result

        # Last Chunk: Start Background Full Analysis
        if chunk_index == total_chunks - 1:
             # Logic is same as before: Count lines, if > limit, background task.
             # Wait, strict adherence to user request "while that 10k rows are loded"
             # If chunk_index > 0, we already returned partial result in chunk 0.
             # So frontend has data. Now we trigger background task to verify if full report is needed.
             # If total_chunks > 1, it IS partial. So full report needed.
             
             with TASK_lock:
                TASKS[file_id] = {'status': 'processing'}
             thread = threading.Thread(target=run_full_analysis, args=(file_id, filepath))
             thread.start()
             response_data['status'] = 'upload_complete'

        return jsonify(response_data)

    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@app.route('/full_report/<file_id>', methods=['GET'])
def get_full_report(file_id):
    with TASK_lock:
        task = TASKS.get(file_id)
    
    if not task:
        return jsonify({'error': 'Task not found'}), 404
    
    if task['status'] in ('processing', 'uploading'):
        return jsonify({'status': task['status']}), 202
    elif task['status'] == 'done':
        return jsonify(task['result']), 200
    else:
        return jsonify({'error': task.get('error')}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5500))
    app.run(host='0.0.0.0', port=port, debug=True)
