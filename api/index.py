"""
Vercel Serverless Function — Money Mule Detection API (Merged)
"""
import os
import io
import time
import networkx as nx
import pandas as pd
from datetime import timedelta
from collections import defaultdict
from flask import Flask, request, jsonify
from flask_cors import CORS

# ─────────────────────────────────────────────────────────────
# GRAPH ENGINE LOGIC (Inlined for Serverless Reliability)
# ─────────────────────────────────────────────────────────────

def parse_csv(file_storage, limit=None):
    """Parse uploaded CSV, handling both column name variants."""
    try:
        df = pd.read_csv(file_storage, nrows=limit)
    except Exception as e:
        raise ValueError(f"Failed to parse CSV: {str(e)}")

    col_map = {}
    for col in df.columns:
        lc = col.strip().lower()
        if lc in ('sender_id', 'sender', 'sender_account', 'source', 'source_account'):
            col_map[col] = 'sender_id'
        elif lc in ('receiver_id', 'receiver', 'receiver_account', 'destination', 'destination_account'):
            col_map[col] = 'receiver_id'
        elif lc in ('amount', 'txn_amount', 'transaction_amount'):
            col_map[col] = 'amount'
        elif lc in ('timestamp', 'date', 'txn_date', 'datetime'):
            col_map[col] = 'timestamp'
        elif lc in ('transaction_id', 'txn_id', 'id'):
            col_map[col] = 'transaction_id'
    df = df.rename(columns=col_map)

    required = ['sender_id', 'receiver_id', 'amount', 'timestamp']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if 'transaction_id' not in df.columns:
        df['transaction_id'] = [f"TXN_{i:05d}" for i in range(1, len(df) + 1)]

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df['amount'] = df['amount'].astype(float)
    return df

def build_graph(df):
    """Build a directed graph from transaction dataframe."""
    G = nx.DiGraph()
    for _, row in df.iterrows():
        sid = str(row['sender_id']).strip()
        rid = str(row['receiver_id']).strip()
        if G.has_edge(sid, rid):
            G[sid][rid]['transactions'].append({
                'transaction_id': row['transaction_id'],
                'amount': row['amount'],
                'timestamp': row['timestamp'],
            })
            G[sid][rid]['total_amount'] += row['amount']
            G[sid][rid]['count'] += 1
        else:
            G.add_edge(sid, rid,
                       transactions=[{
                           'transaction_id': row['transaction_id'],
                           'amount': row['amount'],
                           'timestamp': row['timestamp'],
                       }],
                       total_amount=row['amount'],
                       count=1)
    return G

def _merge_overlapping(groups):
    """Merge groups that share ≥2 members into single rings."""
    if not groups:
        return []
    sets = [set(g) for g in groups]
    merged = True
    while merged:
        merged = False
        new_sets = []
        used = [False] * len(sets)
        for i in range(len(sets)):
            if used[i]:
                continue
            current = sets[i]
            for j in range(i + 1, len(sets)):
                if used[j]:
                    continue
                if len(current & sets[j]) >= 2:
                    current = current | sets[j]
                    used[j] = True
                    merged = True
            new_sets.append(current)
        sets = new_sets
    return [sorted(list(s)) for s in sets]

def detect_cycles(G, min_len=3, max_len=5):
    """Detect unique simple cycles of length 3 to max_len."""
    raw_cycles = []
    seen_sets = set()
    try:
        # Use simple_cycles if available and graph is small enough, else fallback logic could go here
        # For serverless, time limit is tight, so we trust networkx is fast enough for typical demo data
        for cycle in nx.simple_cycles(G, length_bound=max_len):
            if len(cycle) < min_len:
                continue
            key = frozenset(cycle)
            if key in seen_sets:
                continue
            seen_sets.add(key)
            raw_cycles.append(list(cycle))
    except Exception:
        pass # Handle potential timeouts or errors gracefully

    rings = _merge_overlapping(raw_cycles)
    return rings

def _find_best_window(txns, window, threshold):
    """Sliding window to find the first window with ≥ threshold unique peers."""
    i = 0
    for j in range(len(txns)):
        while txns[j]['ts'] - txns[i]['ts'] > window:
            i += 1
        peers = set(t['peer'] for t in txns[i:j + 1])
        if len(peers) >= threshold:
            return list(peers)
    return None

def detect_smurfing(G, df, fan_threshold=10, time_window_hours=72):
    """Detect fan-in and fan-out smurfing patterns within a time window."""
    rings = []
    window = timedelta(hours=time_window_hours)

    # Fan-out
    for node in G.nodes():
        out_edges = list(G.out_edges(node, data=True))
        if len(out_edges) < fan_threshold:
            continue
        txns = []
        for _, recv, data in out_edges:
            for t in data['transactions']:
                txns.append({'peer': recv, 'ts': t['timestamp']})
        if not txns:
            continue
        txns.sort(key=lambda x: x['ts'])
        best_window = _find_best_window(txns, window, fan_threshold)
        if best_window:
            members = sorted(set([node] + best_window))
            rings.append({'type': 'fan_out', 'hub': node, 'members': members})

    # Fan-in
    for node in G.nodes():
        in_edges = list(G.in_edges(node, data=True))
        if len(in_edges) < fan_threshold:
            continue
        txns = []
        for send, _, data in in_edges:
            for t in data['transactions']:
                txns.append({'peer': send, 'ts': t['timestamp']})
        if not txns:
            continue
        txns.sort(key=lambda x: x['ts'])
        best_window = _find_best_window(txns, window, fan_threshold)
        if best_window:
            members = sorted(set([node] + best_window))
            rings.append({'type': 'fan_in', 'hub': node, 'members': members})

    return rings

def detect_shell_networks(G, max_intermediate_degree=3, min_hops=3, exclude_nodes=None):
    """Detect chains of 3+ hops where intermediate accounts have low total degree."""
    exclude = exclude_nodes or set()
    total_degree = {n: G.in_degree(n) + G.out_degree(n) for n in G.nodes()}
    shell_nodes = set(n for n, d in total_degree.items() if d <= max_intermediate_degree) - exclude
    endpoints = set(n for n in G.nodes() if n not in shell_nodes)

    chains = []
    visited_chains = set()

    # DFS from endpoints
    for start in endpoints:
        stack = [(start, [start])]
        while stack:
            current, path = stack.pop()
            # Safety brake for recursion depth in serverless
            if len(path) > 20: continue 
            
            for succ in G.successors(current):
                if succ in set(path):
                    continue
                new_path = path + [succ]
                intermediates = new_path[1:-1]

                if succ not in shell_nodes or len(new_path) > min_hops + 2:
                    if len(intermediates) >= min_hops and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            chains.append(new_path)
                elif succ in shell_nodes:
                    stack.append((succ, new_path))
                    if len(intermediates) >= min_hops and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        visited_chains.add(chain_key)
                        chains.append(new_path)

    # DFS from shell nodes (pure shell chains)
    for start in shell_nodes:
        stack = [(start, [start])]
        while stack:
            current, path = stack.pop()
            if len(path) > 20: continue

            for succ in G.successors(current):
                if succ in set(path): continue
                new_path = path + [succ]
                if len(new_path) >= min_hops + 1:
                    intermediates = new_path[1:-1]
                    if intermediates and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            chains.append(new_path)
                if succ in shell_nodes:
                    stack.append((succ, new_path))

    return _merge_overlapping(chains)

def identify_legitimate_accounts(G, df):
    """Identify likely merchants or payroll accounts."""
    legitimate = set()
    for node in G.nodes():
        in_deg = G.in_degree(node)
        out_deg = G.out_degree(node)

        if in_deg >= 100 and out_deg == 0:
            legitimate.add(node)
            continue
        if out_deg >= 100 and in_deg == 0:
            legitimate.add(node)
            continue

        if in_deg >= 20:
            senders = set(s for s, _ in G.in_edges(node))
            if len(senders) >= 15:
                # Simplified check for speed
                legitimate.add(node)

        if out_deg >= 20:
            receivers = set(r for _, r in G.out_edges(node))
            if len(receivers) >= 15:
                legitimate.add(node)
    return legitimate

def _get_edge_timestamps(G, path, is_cycle=False):
    timestamps = []
    for i in range(len(path) - 1):
        src, dst = path[i], path[i + 1]
        if G.has_edge(src, dst):
            timestamps.extend(t['timestamp'] for t in G[src][dst]['transactions'])
    if is_cycle and len(path) >= 2:
        src, dst = path[-1], path[0]
        if G.has_edge(src, dst):
            timestamps.extend(t['timestamp'] for t in G[src][dst]['transactions'])
    return timestamps

def _time_span_hours(timestamps):
    if len(timestamps) < 2:
        return float('inf')
    ts_sorted = sorted(timestamps)
    return (ts_sorted[-1] - ts_sorted[0]).total_seconds() / 3600

def _build_graph_viz(G, account_scores, fraud_rings):
    suspicious_set = set(a for a, info in account_scores.items() if info['score'] > 0)
    account_ring_map = defaultdict(set)
    for ring in fraud_rings:
        for acc in ring['member_accounts']:
            account_ring_map[acc].add(ring['ring_id'])

    nodes = []
    for node in G.nodes():
        info = account_scores.get(node, {'score': 0, 'ring_ids': set()})
        nodes.append({
            'id': node,
            'suspicious': node in suspicious_set,
            'score': round(info['score'], 1) if isinstance(info['score'], (int, float)) else 0,
            'ring_ids': sorted(list(account_ring_map.get(node, set()))),
            'in_degree': G.in_degree(node),
            'out_degree': G.out_degree(node),
        })

    edges = []
    for src, dst, data in G.edges(data=True):
        edges.append({
            'source': src,
            'target': dst,
            'total_amount': round(data['total_amount'], 2),
            'count': data['count'],
        })

    return {'nodes': nodes, 'edges': edges}

def analyze(file_storage, limit=None):
    """Run full analysis pipeline."""
    start = time.time()
    df = parse_csv(file_storage, limit=limit)
    rows_processed = len(df)
    is_partial = limit and rows_processed >= limit

    G = build_graph(df)
    all_accounts = set(df['sender_id'].unique()) | set(df['receiver_id'].unique())

    cycle_rings = detect_cycles(G)
    smurfing_rings = detect_smurfing(G, df)
    
    cycle_members = set(acc for ring in cycle_rings for acc in ring)
    shell_rings = detect_shell_networks(G, exclude_nodes=cycle_members)
    legitimate = identify_legitimate_accounts(G, df)

    fraud_rings = []
    account_scores = defaultdict(lambda: {'score': 0.0, 'patterns': set(), 'ring_ids': set()})
    ring_counter = 0

    # Process Rings logic (Simplified for brevity but functionally identical)
    # Cycles
    for members in cycle_rings:
        if not (3 <= len(members) <= 5): continue
        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"
        timestamps = _get_edge_timestamps(G, members, is_cycle=True)
        span = _time_span_hours(timestamps)
        velocity_bonus = 15 if span < 24 else (5 if span < 72 else 0)
        
        for acc in members:
            account_scores[acc]['score'] += 40 + velocity_bonus
            account_scores[acc]['patterns'].add(f"cycle_length_{len(members)}")
            if velocity_bonus > 0: account_scores[acc]['patterns'].add("high_velocity")
            account_scores[acc]['ring_ids'].add(ring_id)
        
        fraud_rings.append({
            'ring_id': ring_id, 'member_accounts': members, 'pattern_type': 'cycle',
            'risk_score': min(100.0, float(40 + velocity_bonus)), 'transaction_count': len(timestamps)
        })

    # Smurfing
    for smurf in smurfing_rings:
        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"
        for acc in smurf['members']:
            account_scores[acc]['score'] += 30
            account_scores[acc]['patterns'].add(smurf['type'])
            account_scores[acc]['ring_ids'].add(ring_id)
        
        tx_count = 0
        hub = smurf['hub']
        if smurf['type'] == 'fan_out':
            for m in smurf['members']:
                if m != hub and G.has_edge(hub, m): tx_count += G[hub][m]['count']
        elif smurf['type'] == 'fan_in':
            for m in smurf['members']:
                if m != hub and G.has_edge(m, hub): tx_count += G[m][hub]['count']

        fraud_rings.append({
            'ring_id': ring_id, 'member_accounts': smurf['members'], 'pattern_type': smurf['type'],
            'risk_score': 30.0, 'transaction_count': tx_count
        })

    # Shells
    for members in shell_rings:
        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"
        timestamps = _get_edge_timestamps(G, members)
        span = _time_span_hours(timestamps)
        velocity_bonus = 10 if span < 24 else 0
        
        for acc in members:
            account_scores[acc]['score'] += 25 + velocity_bonus
            account_scores[acc]['patterns'].add("layered_shell")
            if velocity_bonus > 0: account_scores[acc]['patterns'].add("rapid_layering")
            account_scores[acc]['ring_ids'].add(ring_id)
            
        fraud_rings.append({
            'ring_id': ring_id, 'member_accounts': members, 'pattern_type': 'layered_shell',
            'risk_score': min(100.0, float(25 + velocity_bonus)), 'transaction_count': len(timestamps)
        })

    # Scoring cleanup
    for acc in legitimate:
        if acc in account_scores:
            account_scores[acc]['score'] = max(0, account_scores[acc]['score'] - 50)
            account_scores[acc]['patterns'].add("merchant_exception")
            
    for acc in account_scores:
        account_scores[acc]['score'] = min(100.0, account_scores[acc]['score'])
        
    for ring in fraud_rings:
        scores = [account_scores[a]['score'] for a in ring['member_accounts']]
        ring['risk_score'] = float(round(sum(scores)/len(scores), 1)) if scores else 0.0

    suspicious_accounts = []
    for acc, info in account_scores.items():
        if info['score'] <= 0: continue
        for rid in sorted(info['ring_ids']):
            suspicious_accounts.append({
                'account_id': acc,
                'suspicion_score': float(round(info['score'], 1)),
                'detected_patterns': sorted(list(info['patterns'] - {'merchant_exception'})),
                'ring_id': rid
            })
    
    suspicious_accounts.sort(key=lambda x: (-x['suspicion_score'], x['account_id']))

    return {
        'suspicious_accounts': suspicious_accounts,
        'fraud_rings': fraud_rings,
        'summary': {
            'total_accounts_analyzed': len(all_accounts),
            'suspicious_accounts_flagged': len(set(sa['account_id'] for sa in suspicious_accounts)),
            'fraud_rings_detected': len(fraud_rings),
            'processing_time_seconds': round(time.time() - start, 2),
            'rows_processed': rows_processed,
            'is_partial': is_partial
        },
        'graph': _build_graph_viz(G, account_scores, fraud_rings),
    }

# ─────────────────────────────────────────────────────────────
# FLASK APP
# ─────────────────────────────────────────────────────────────

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
        content = file.read().decode('utf-8', errors='ignore')
        string_io = io.StringIO(content)
        result = analyze(string_io)
        return jsonify(result)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Analysis failed: {str(e)}'}), 500

@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'engine': 'MuleWatch Serverless Embedded',
        'libraries': {
            'networkx': nx.__version__,
            'pandas': pd.__version__
        }
    })
