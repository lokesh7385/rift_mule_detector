"""
Graph-based Money Muling Detection Engine
Detects: Cycles (3-5), Smurfing (Fan-in/Fan-out), Layered Shell Networks
Includes false-positive guards for merchants and payroll accounts.
"""

import networkx as nx
import pandas as pd
from datetime import timedelta
from collections import defaultdict
import time


# ─────────────────────────────────────────────────────────────
# CSV PARSING
# ─────────────────────────────────────────────────────────────

def parse_csv(file_storage, limit=None):
    """Parse uploaded CSV, handling both column name variants."""
    df = pd.read_csv(file_storage, nrows=limit)
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

    if 'transaction_id' not in df.columns:
        df['transaction_id'] = [f"TXN_{i:05d}" for i in range(1, len(df) + 1)]

    df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
    df['amount'] = df['amount'].astype(float)
    return df


# ─────────────────────────────────────────────────────────────
# GRAPH CONSTRUCTION
# ─────────────────────────────────────────────────────────────

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


# ─────────────────────────────────────────────────────────────
# 1. CYCLE DETECTION (length 3-5)
# ─────────────────────────────────────────────────────────────

def detect_cycles(G, min_len=3, max_len=5):
    """Detect unique simple cycles of length 3 to max_len.
    Merges overlapping cycles into single rings."""
    raw_cycles = []
    seen_sets = set()
    try:
        for cycle in nx.simple_cycles(G, length_bound=max_len):
            if len(cycle) < min_len:
                continue
            key = frozenset(cycle)
            if key in seen_sets:
                continue
            seen_sets.add(key)
            raw_cycles.append(list(cycle))
    except Exception:
        pass

    # Merge overlapping cycles into consolidated rings
    rings = _merge_overlapping(raw_cycles)
    return rings


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


# ─────────────────────────────────────────────────────────────
# 2. SMURFING (Fan-in / Fan-out) with 72h window
# ─────────────────────────────────────────────────────────────

def detect_smurfing(G, df, fan_threshold=10, time_window_hours=72):
    """Detect fan-in and fan-out smurfing patterns within a time window."""
    rings = []
    window = timedelta(hours=time_window_hours)

    # Fan-out: one sender -> many receivers
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

    # Fan-in: many senders -> one receiver
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


# ─────────────────────────────────────────────────────────────
# 3. LAYERED SHELL NETWORKS
# ─────────────────────────────────────────────────────────────

def detect_shell_networks(G, max_intermediate_degree=3, min_hops=3, exclude_nodes=None):
    """Detect chains of 3+ hops where intermediate accounts have
    low total transaction counts (≤ max_intermediate_degree).
    exclude_nodes: set of accounts already identified in cycle rings (won't be shell intermediates).
    Returns consolidated shell rings (merged overlapping chains)."""
    exclude = exclude_nodes or set()
    total_degree = {n: G.in_degree(n) + G.out_degree(n) for n in G.nodes()}
    shell_nodes = set(n for n, d in total_degree.items() if d <= max_intermediate_degree) - exclude

    # Non-shell nodes are potential chain endpoints
    endpoints = set(n for n in G.nodes() if n not in shell_nodes)

    chains = []
    visited_chains = set()

    for start in endpoints:
        # DFS from endpoints through shell intermediates
        stack = [(start, [start])]
        while stack:
            current, path = stack.pop()
            for succ in G.successors(current):
                if succ in set(path):
                    continue
                new_path = path + [succ]
                intermediates = new_path[1:-1]

                # If we hit a non-shell node (or end of chain), check
                if succ not in shell_nodes or len(new_path) > min_hops + 2:
                    if len(intermediates) >= min_hops and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            chains.append(new_path)
                elif succ in shell_nodes and len(new_path) <= min_hops + 2:
                    # Keep extending through shell nodes
                    stack.append((succ, new_path))
                    # Also check if current path already qualifies
                    if len(intermediates) >= min_hops and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            chains.append(new_path)

    # Also: any path with 3+ hops through low-degree intermediates
    # (start may also be shell if it's the beginning of a pure shell chain)
    for start in shell_nodes:
        stack = [(start, [start])]
        while stack:
            current, path = stack.pop()
            for succ in G.successors(current):
                if succ in set(path):
                    continue
                new_path = path + [succ]
                if len(new_path) >= min_hops + 1:
                    intermediates = new_path[1:-1]
                    if intermediates and all(n in shell_nodes for n in intermediates):
                        chain_key = frozenset(new_path)
                        if chain_key not in visited_chains:
                            visited_chains.add(chain_key)
                            chains.append(new_path)
                if succ in shell_nodes and len(new_path) <= min_hops + 2:
                    stack.append((succ, new_path))

    # Merge overlapping chains
    rings = _merge_overlapping(chains)
    return rings


# ─────────────────────────────────────────────────────────────
# FALSE POSITIVE GUARDS
# ─────────────────────────────────────────────────────────────

def identify_legitimate_accounts(G, df):
    """Identify likely merchants or payroll accounts (high-volume, regular patterns)."""
    legitimate = set()
    for node in G.nodes():
        in_deg = G.in_degree(node)
        out_deg = G.out_degree(node)

        # 1. High-Volume Merchant (Grocery Store Rule)
        # 100+ incoming transactions, 0 outgoing -> clearly a sink for legitimate funds.
        if in_deg >= 100 and out_deg == 0:
            legitimate.add(node)
            continue

        # 2. Pure Payroll Source
        # 100+ outgoing transactions, 0 incoming -> clearly a source (e.g., corporate account).
        if out_deg >= 100 and in_deg == 0:
            legitimate.add(node)
            continue

        # Merchant: high in-degree, many unique senders, consistent amounts
        if in_deg >= 20:
            senders = set(s for s, _ in G.in_edges(node))
            amounts = []
            for s, _, data in G.in_edges(node, data=True):
                amounts.extend(t['amount'] for t in data['transactions'])
            if len(senders) >= 15 and amounts:
                avg = sum(amounts) / len(amounts)
                std = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5
                cv = std / avg if avg > 0 else 0
                if cv < 0.3:
                    legitimate.add(node)

        # Payroll: high out-degree, many receivers, consistent amounts
        if out_deg >= 20:
            receivers = set(r for _, r in G.out_edges(node))
            amounts = []
            for _, r, data in G.out_edges(node, data=True):
                amounts.extend(t['amount'] for t in data['transactions'])
            if len(receivers) >= 15 and amounts:
                avg = sum(amounts) / len(amounts)
                std = (sum((a - avg) ** 2 for a in amounts) / len(amounts)) ** 0.5
                cv = std / avg if avg > 0 else 0
                if cv < 0.3:
                    legitimate.add(node)

    return legitimate


# ─────────────────────────────────────────────────────────────
# SUSPICION SCORING & JSON OUTPUT
# ─────────────────────────────────────────────────────────────

def _get_edge_timestamps(G, path, is_cycle=False):
    """Collect all timestamps along a path (or cycle)."""
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
    """Return the time span in hours for a list of timestamps."""
    if len(timestamps) < 2:
        return float('inf')
    ts_sorted = sorted(timestamps)
    return (ts_sorted[-1] - ts_sorted[0]).total_seconds() / 3600


def analyze(file_storage, limit=None):
    """Run full analysis pipeline. Returns JSON-ready dict.
    limit: Max rows to read (for initial glimpse)."""
    start = time.time()

    df = parse_csv(file_storage, limit=limit)
    
    # ── Performance / Metadata ──
    rows_processed = len(df)
    is_partial = False
    if limit and rows_processed >= limit:
         is_partial = True

    G = build_graph(df)
    all_accounts = set(df['sender_id'].unique()) | set(df['receiver_id'].unique())

    # ── Detect patterns ──
    cycle_rings = detect_cycles(G)
    smurfing_rings = detect_smurfing(G, df)
    # Exclude cycle-ring nodes from being shell intermediates
    cycle_members = set(acc for ring in cycle_rings for acc in ring)
    shell_rings = detect_shell_networks(G, exclude_nodes=cycle_members)
    legitimate = identify_legitimate_accounts(G, df)

    # ── Build fraud_rings array and score accounts ──
    fraud_rings = []
    account_scores = defaultdict(lambda: {'score': 0.0, 'patterns': set(), 'ring_ids': set()})
    ring_counter = 0

    # Cycle rings
    for members in cycle_rings:
        cycle_len = len(members)
        # Filter: Only include cycles of length 3 to 5
        if not (3 <= cycle_len <= 5):
            continue

        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"

        # Temporal analysis on cycle edges
        timestamps = _get_edge_timestamps(G, members, is_cycle=True)
        span = _time_span_hours(timestamps)
        velocity_bonus = 15 if span < 24 else (5 if span < 72 else 0)

        for acc in members:
            account_scores[acc]['score'] += 40 + velocity_bonus
            account_scores[acc]['patterns'].add(f"cycle_length_{cycle_len}")
        if velocity_bonus > 0:
            account_scores[acc]['patterns'].add("high_velocity")
        account_scores[acc]['ring_ids'].add(ring_id)

        member_risk = min(100, 40 + velocity_bonus)
        fraud_rings.append({
            'ring_id': ring_id,
            'member_accounts': members,
            'pattern_type': 'cycle',
            'risk_score': float(round(member_risk, 1)),
            'transaction_count': len(timestamps),
        })

    # Smurfing rings
    for smurf in smurfing_rings:
        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"
        for acc in smurf['members']:
            account_scores[acc]['score'] += 30
            account_scores[acc]['patterns'].add(smurf['type'])
            account_scores[acc]['ring_ids'].add(ring_id)

        # Calculate transaction count for smurfing
        tx_count = 0
        hub = smurf['hub']
        if smurf['type'] == 'fan_out':
            for m in smurf['members']:
                if m != hub and G.has_edge(hub, m):
                    tx_count += G[hub][m]['count']
        elif smurf['type'] == 'fan_in':
            for m in smurf['members']:
                if m != hub and G.has_edge(m, hub):
                    tx_count += G[m][hub]['count']

        fraud_rings.append({
            'ring_id': ring_id,
            'member_accounts': smurf['members'],
            'pattern_type': smurf['type'],
            'risk_score': 30.0,
            'transaction_count': tx_count,
        })

    # Shell network rings
    for members in shell_rings:
        ring_counter += 1
        ring_id = f"RING_{ring_counter:03d}"

        timestamps = _get_edge_timestamps(G, members)
        span = _time_span_hours(timestamps)
        velocity_bonus = 10 if span < 24 else 0

        for acc in members:
            account_scores[acc]['score'] += 25 + velocity_bonus
            account_scores[acc]['patterns'].add("layered_shell")
            if velocity_bonus > 0:
                account_scores[acc]['patterns'].add("rapid_layering")
            account_scores[acc]['ring_ids'].add(ring_id)

        fraud_rings.append({
            'ring_id': ring_id,
            'member_accounts': members,
            'pattern_type': 'layered_shell',
            'risk_score': float(round(25 + velocity_bonus, 1)),
            'transaction_count': len(timestamps),
        })

    # ── Apply false positive penalties ──
    for acc in legitimate:
        if acc in account_scores:
            account_scores[acc]['score'] = max(0, account_scores[acc]['score'] - 50)
            account_scores[acc]['patterns'].add("merchant_or_payroll_exception")

    # ── Cap scores at 100 ──
    for acc in account_scores:
        account_scores[acc]['score'] = min(100.0, account_scores[acc]['score'])

    # ── Compute risk_score for each ring as average of member scores ──
    for ring in fraud_rings:
        member_scores = [account_scores[a]['score'] for a in ring['member_accounts']]
        ring['risk_score'] = float(round(sum(member_scores) / len(member_scores), 1)) if member_scores else 0.0

    # ── Build suspicious_accounts (one entry per account-ring pair) ──
    suspicious_accounts = []
    for acc, info in account_scores.items():
        if info['score'] <= 0:
            continue
        patterns = sorted(info['patterns'] - {'merchant_or_payroll_exception'})
        ring_ids_sorted = sorted(info['ring_ids'])
        # One entry per ring_id for the account
        for rid in ring_ids_sorted:
            suspicious_accounts.append({
                'account_id': acc,
                'suspicion_score': float(round(info['score'], 1)),
                'detected_patterns': patterns,
                'ring_id': rid,
            })

    # Sort by suspicion_score descending, then account_id
    suspicious_accounts.sort(key=lambda x: (-x['suspicion_score'], x['account_id']))

    elapsed = round(time.time() - start, 2)

    # ── Build result ──
    result = {
        'suspicious_accounts': suspicious_accounts,
        'fraud_rings': fraud_rings,
        'summary': {
            'total_accounts_analyzed': len(all_accounts),
            'suspicious_accounts_flagged': len(set(sa['account_id'] for sa in suspicious_accounts)),
            'fraud_rings_detected': len(fraud_rings),
            'processing_time_seconds': elapsed,
            'rows_processed': rows_processed,
            'is_partial': is_partial
        },
        'graph': _build_graph_viz(G, account_scores, fraud_rings),
    }

    return result


def _build_graph_viz(G, account_scores, fraud_rings):
    """Build visualization data for Cytoscape.js."""
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
