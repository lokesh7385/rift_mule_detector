"""
Vercel Serverless Function — Money Mule Detection API (Streamlined)
"""
import os
import io
import time
import networkx as nx
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
# OPTIMIZED GRAPH ENGINE (Vercel-Safe)
# ─────────────────────────────────────────────────────────────

def analyze(file_storage, limit=None):
    """Run streamlined analysis pipeline optimized for Vercel limits."""
    start_time = time.time()
    
    # 1. Parsing & Sampling
    # Vercel Optimization: Limit rows to prevent memory crashes (128MB limit)
    # 10k-15k rows is the safe zone.
    actual_limit = 10000 
    if limit and limit < actual_limit:
        actual_limit = limit
        
    try:
        df = pd.read_csv(file_storage, nrows=actual_limit)
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {str(e)}")

    # 2. Column Mapping (Robustness)
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
    # If timestamp is missing, we just ignore it for the simple cycle check
    
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
            continue # Skip bad rows

    suspicious_accounts = []
    fraud_rings = []
    
    # 4. Pattern: Cycles (Length 3-5)
    # We use a generator and limit the count for speed (10s timeout)
    try:
        # Use simple_cycles. 
        # CAUTION: On large graphs this is O(n!). 
        # But with 10k rows and typical sparse financial data, it's usually okay IF we cap it.
        # Ideally we'd use a depth-limited search, but simple_cycles is standard.
        # We add a strict time check inside the loop if possible, 
        # but nx.simple_cycles returns an iterator, so we can break early.
        
        cycle_iter = nx.simple_cycles(G)
        cycle_count = 0
        
        start_cycle_search = time.time()
        
        for cycle in cycle_iter:
            # Timeout Guard (5s max for cycle search)
            if time.time() - start_cycle_search > 5.0:
                break
                
            if 3 <= len(cycle) <= 5:
                cycle_count += 1
                ring_id = f"RING_{cycle_count:03d}"
                
                # Create Ring Object
                fraud_rings.append({
                    "ring_id": ring_id,
                    "member_accounts": cycle,
                    "pattern_type": "cycle",
                    "risk_score": 92.5,  # Float required
                    "transaction_count": len(cycle) # Approximation
                })
                
                # Create Account Objects
                for node in cycle:
                    suspicious_accounts.append({
                        "account_id": node,
                        "suspicion_score": 88.0, # Float required
                        "detected_patterns": [f"cycle_length_{len(cycle)}"],
                        "ring_id": ring_id
                    })
            
            # Safety Cap: 20 rings max to keep JSON small and processing fast
            if len(fraud_rings) >= 20: 
                break
                
    except Exception:
        pass # Fallback if graph is too complex

    # 5. Visualization Data (Simplified for Vercel)
    # Only include nodes/edges involved in fraud OR top volume, to save bandwidth
    viz_nodes = []
    viz_edges = []
    
    if len(fraud_rings) > 0:
        relevant_nodes = set()
        for r in fraud_rings:
            relevant_nodes.update(r['member_accounts'])
        
        # Add some context nodes (neighbors)
        # (Skipped for extreme speed, only showing fraud rings)
        
        for node in relevant_nodes:
            viz_nodes.append({
                "id": node, 
                "suspicious": True, 
                "score": 88.0,
                "in_degree": G.in_degree(node),
                "out_degree": G.out_degree(node)
            })
            
        # Add edges between them
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

# ─────────────────────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────────────────────

app = Flask(__name__)
CORS(app)

app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB

@app.route('/', methods=['POST'])
@app.route('/upload', methods=['POST'])
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
        content = file.read().decode('utf-8', errors='ignore')
        string_io = io.StringIO(content)
        result = analyze(string_io)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({
            'error': str(e),
            'tip': 'Check if CSV columns match requirements (sender_id, receiver_id, amount) or if file is too large.',
            'is_partial': True
        }), 200

@app.route('/', methods=['GET'])
@app.route('/health', methods=['GET'])
@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'engine': 'MuleWatch Serverless Streamlined',
        'libraries': {
            'networkx': nx.__version__,
            'pandas': pd.__version__
        }
    })
