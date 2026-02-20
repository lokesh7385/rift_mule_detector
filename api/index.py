"""
Vercel Serverless Function — Money Mule Detection API
"""
import os
import io
from flask import Flask, request, jsonify
from flask_cors import CORS
from graph_engine import analyze

app = Flask(__name__)
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB


@app.route('/api/upload', methods=['POST'])
def upload():
    """Handle CSV upload and run analysis."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not file.filename.lower().endswith('.csv'):
        return jsonify({'error': 'Only CSV files are accepted'}), 400

    try:
        # Read file into memory (serverless — no persistent disk)
        content = file.read().decode('utf-8', errors='ignore')
        string_io = io.StringIO(content)

        result = analyze(string_io)
        return jsonify(result)

    except Exception as e:
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'engine': 'MuleWatch v2.0'})
