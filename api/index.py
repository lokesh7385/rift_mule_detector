"""
Vercel Serverless Function — Money Mule Detection API (Lazy Loading)
"""
import os
import sys
import io
import time
import json
from flask import Flask, request, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
# FLASK APP (Must be top-level for Vercel Scanner)
# ─────────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 

# ─────────────────────────────────────────────────────────────
# OPTIMIZED GRAPH ENGINE (Lazy Loaded)
# ─────────────────────────────────────────────────────────────

def analyze(file_storage, limit=None):
    """Run streamlined analysis pipeline optimized for Vercel limits."""
    # Lazy Import to prevent Cold Start Crash
    try:
        import networkx as nx
        import pandas as pd
        import numpy as np
    except ImportError as e:
         raise ImportError(f"Critical Dependency Missing: {str(e)} | Paths: {sys.path}")

    start_time = time.time()
    
    # 1. Parsing & Sampling
    actual_limit = 10000 
    if limit and limit < actual_limit:
        actual_limit = limit
        
    try:
        df = pd.read_csv(file_storage, nrows=actual_limit)
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {str(e)}")

    # 2. Column Mapping
    col_map = {}
    for col in df.columns:
        lc = col.strip().lower()
        if lc in ('sender_id', 'sender', 'nameorig', 'source'):
            col_map[col] = 'sender_id'
        elif lc in ('receiver_id', 'receiver', 'namedest', 'destination'):
            col_map[col] = 'receiver_id'
        elif lc in ('amount', 'txn_amount'):
            col_map[col] = 'amount'
    df = df.rename(columns=col_map)
    
    required = ['sender_id', 'receiver_id', 'amount']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # 3. Build Graph
    G = nx.DiGraph()
    for _, row in df.iterrows():
        try:
            amt = float(row['amount'])
            G.add_edge(str(row['sender_id']), str(row['receiver_id']), amount=amt)
        except ValueError:
            continue 

    suspicious_accounts = []
    fraud_rings = []
    
    # 4. Pattern: Cycles (Length 3-5)
    try:
        cycle_iter = nx.simple_cycles(G)
        cycle_count = 0
        start_cycle_search = time.time()
        
        for cycle in cycle_iter:
            # Timeout Guard (5s)
            if time.time() - start_cycle_search > 5.0:
                break
                
            if 3 <= len(cycle) <= 5:
                cycle_count += 1
                ring_id = f"RING_{cycle_count:03d}"
                
                fraud_rings.append({
                    "ring_id": ring_id,
                    "member_accounts": cycle,
                    "pattern_type": "cycle",
                    "risk_score": 92.5,
                    "transaction_count": len(cycle)
                })
                
                for node in cycle:
                    suspicious_accounts.append({
                        "account_id": node,
                        "suspicion_score": 88.0,
                        "detected_patterns": [f"cycle_length_{len(cycle)}"],
                        "ring_id": ring_id
                    })
            
            if len(fraud_rings) >= 20: 
                break
    except Exception:
        pass 

    # 5. Visualization Data 
    viz_nodes = []
    viz_edges = []
    
    if len(fraud_rings) > 0:
        relevant_nodes = set()
        for r in fraud_rings:
            relevant_nodes.update(r['member_accounts'])
        
        for node in relevant_nodes:
            viz_nodes.append({
                "id": node, 
                "suspicious": True, 
                "score": 88.0,
                "in_degree": G.in_degree(node) if G.has_node(node) else 0,
                "out_degree": G.out_degree(node) if G.has_node(node) else 0
            })
            
        subgraph = G.subgraph(relevant_nodes)
        for u, v, data in subgraph.edges(data=True):
            viz_edges.append({
                "source": u, 
                "target": v, 
                "total_amount": data.get('amount', 0.0)
            })

    return {
        "suspicious_accounts": suspicious_accounts,
        "fraud_rings": fraud_rings,
        "summary": {
            "total_accounts_analyzed": len(G.nodes()),
            "suspicious_accounts_flagged": len(suspicious_accounts),
            "fraud_rings_detected": len(fraud_rings),
            "processing_time_seconds": round(time.time() - start_time, 3),
            "rows_processed": len(df),
            "is_partial": True
        },
        "graph": {
            "nodes": viz_nodes,
            "edges": viz_edges
        }
    }

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health():
    # Only verify flask/basic imports here
    return jsonify({
        'status': 'ok',
        'engine': 'MuleWatch Serverless (Lazy Load)',
        'note': 'Pandas/NetworkX load only on upload'
    })

@app.route('/upload', methods=['POST'])
@app.route('/api/upload', methods=['POST'])
def upload_route():
    try:
        # Check files
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        if not file.filename.lower().endswith('.csv'):
            return jsonify({'error': 'Only CSV files are accepted'}), 400

        content = file.read().decode('utf-8', errors='ignore')
        result = analyze(io.StringIO(content))
        return jsonify(result)

    except ImportError as e:
        return jsonify({
            "error": "Dependency Missing",
            "message": str(e),
            "hint": "Pandas/NetworkX not installed or failed to load."
        }), 500
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'trace': traceback.format_exc()
        }), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
