# RIFT Mule Detector — Financial Forensics Engine

> **RIFT 2026 Hackathon | Graph Theory / Financial Crime Detection Track**

A web-based Financial Forensics Engine that processes transaction CSV data and exposes **money muling networks** through graph analysis and interactive visualization.

---

## 🔗 Live Demo

> *(Deployment URL to be added after hosting)*

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 + Flask |
| Graph Analysis | NetworkX |
| Data Processing | Pandas |
| Frontend | Vanilla HTML / CSS / JavaScript |
| Graph Visualization | Cytoscape.js |
| Deployment | Render (Gunicorn) |

---

## 🏗 System Architecture

```
CSV Upload
    │
    ▼
Flask /upload endpoint (app.py)
    │
    ▼
graph_engine.py
    ├── parse_csv()           — normalize column names, parse timestamps
    ├── build_graph()         — NetworkX DiGraph: nodes=accounts, edges=transactions
    ├── detect_cycles()       — simple_cycles(), length 3–5, merge overlapping
    ├── detect_smurfing()     — fan-in / fan-out with 72-hour sliding window
    ├── detect_shell_networks() — DFS through low-degree intermediates (≤3 txns)
    ├── identify_legitimate_accounts() — merchant/payroll false-positive guard
    └── analyze()            — orchestrates all detectors → JSON result
    │
    ▼
JSON Response → Cytoscape.js (graph viz) + Tables + Download
```

---

## 🔍 Algorithm Approach

### 1. Cycle Detection (Circular Fund Routing)
- Uses NetworkX `simple_cycles()` with `length_bound=5`
- Filters cycles of length **3 to 5**
- Overlapping cycles sharing ≥2 members are **merged** into a single ring
- **Complexity**: O(V + E) per cycle enumeration (Johnson's algorithm) — O((V+E)(C+1)) total where C = number of simple cycles

### 2. Smurfing (Fan-in / Fan-out)
- For each node: collect all outgoing (or incoming) transactions with timestamps
- Sort by timestamp, apply a **72-hour sliding window**
- If ≥10 unique receivers (fan-out) or ≥10 unique senders (fan-in) in any window → suspicious ring
- **Complexity**: O(V · T log T) where T = max transactions per node

### 3. Layered Shell Networks
- Compute total degree (in + out) per node
- Shell nodes = accounts with total degree ≤ 3
- DFS from non-shell source nodes through contiguous shell intermediates
- A chain qualifies if it has ≥3 shell hops between endpoints
- **Complexity**: O(V · E) worst case

### 4. False Positive Guards
- **High-Volume Merchant Rule**: 100+ incoming transactions, 0 outgoing → classified as legitimate sink (e.g., Grocery Store)
- **Pure Payroll Rule**: 100+ outgoing transactions, 0 incoming → classified as legitimate source (e.g., Corporate Payroll)
- **Merchant trap (statistical)**: high in-degree (≥20) + many unique senders (≥15) + low coefficient of variation in amounts → excluded
- **Payroll trap (statistical)**: high out-degree (≥20) + many receivers (≥15) + consistent amounts → excluded
- Exclusion method: -50 point penalty on suspicion score (cannot go below 0)

---

## 📊 Suspicion Score Methodology

Each account receives a composite score (0–100):

| Pattern Detected | Base Score |
|-----------------|-----------|
| Cycle participation | +40 |
| Transactions within 24h | +15 (velocity bonus) |
| Transactions within 72h | +5 (velocity bonus) |
| Smurfing involvement | +30 |
| Shell network chain | +25 |
| Rapid layering (<24h) | +10 |
| Merchant/Payroll exception | −50 |

Final score is capped at 100. Accounts are sorted descending by score in the output JSON.

---

## 📁 Project Structure

```
rift_mule_detector/
├── backend/
│   ├── app.py              # Flask server — serves UI + /upload endpoint
│   ├── graph_engine.py     # All graph detection algorithms
│   └── static/
│       ├── index.html      # Single-page UI
│       ├── style.css       # Dark glassmorphic design
│       └── app.js          # Cytoscape.js viz + table rendering
├── sample_data.csv         # Sample dataset with known patterns
├── requirements.txt        # Python dependencies
├── render.yaml             # Render deployment config
└── README.md
```

---

## ⚙️ Installation & Setup

```bash
# 1. Clone the repository
git clone https://github.com/<your-username>/rift_mule_detector.git
cd rift_mule_detector

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

> **Troubleshooting (Windows PowerShell)**: If you see an error about `Execution_Policies`, run one of the following commands **before** activating:
> - `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (Current session only)
> - `Set-ExecutionPolicy RemoteSigned` (Persistent change)
>
> Alternatively, switch to Command Prompt (`cmd`) or Git Bash.

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the development server
cd backend
python app.py
# Open http://localhost:5000
```

---

## 📖 Usage

1. Open the app in your browser
2. Drag & drop your CSV file onto the upload zone (or click to browse)
3. Required CSV columns: `transaction_id`, `sender_id` (or `sender`), `receiver_id` (or `receiver`), `amount`, `timestamp`
4. Click **Download JSON Report** to get the full analysis in the required format
5. Click any suspicious node in the graph to highlight its entire fraud ring

---

## ⚠️ Known Limitations

- Cycle detection limited to length ≤5 (performance constraint for large graphs)
- Shell detection uses a degree threshold of ≤3 — may miss intermediates with slightly higher activity
- Fan-in/fan-out threshold is fixed at 10 — datasets with different normal transaction volumes may need tuning
- False positive guards for merchants/payroll require ≥20 in/out-degree to trigger — smaller legitimate aggregators may still get flagged
- Processing time for very large datasets (>10K transactions) may approach the 30s limit

---

## 👥 Team Members

> *(Add your team member names here)*

---

*RIFT 2026 Hackathon — Graph Theory Track — Money Muling Detection Challenge*
