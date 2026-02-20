# MuleWatch: Financial Crime Detection Engine 🕵️‍♂️💸

> **Live Application**: [https://rift-mule-detector.vercel.app](https://rift-mule-detector.vercel.app)

**MuleWatch** is a serverless financial forensics engine designed to detect complex money laundering networks (smurfing, cycles, and mule rings) in real-time. Built for the RIFT 2026 Challenge.

---

## 🏗️ System Architecture

```mermaid
graph TD
    User[Investigator] -->|Uploads CSV| Frontend[Frontend (Vercel Static)]
    Frontend -->|POST /api/upload| API[Serverless API (Flask)]
    
    subgraph "Detection Engine (Python)"
        API --> Parser[CSV Parser &Sampler]
        Parser --> Graph[NetworkX Graph Builder]
        Graph --> Cycle[Cycle Detection (L3-L5)]
        Graph --> Smurf[Smurfing/Fan-Out Detection]
        Cycle --> Score[Risk Scoring Logic]
        Smurf --> Score
    end
    
    Score --> JSON[JSON Report]
    JSON -->|Response| Frontend
    Frontend -->|Render| Viz[Cytoscape Graph & Data Tables]
```

---

## 🧠 Detection Algorithms

The engine employs a multi-layered graph analysis approach:

### 1. Cycle Detection (The "Round Tripper")
*   **Logic**: Identifies closed loops of transactions (`A -> B -> C -> A`) often used to artificially inflate transaction volume or layer funds.
*   **Optimization**: Restricted to cycle lengths of 3 to 5 nodes to prioritize high-confidence rings and respect serverless timeouts.
*   **Scoring**: High impact on Risk Score (92.5%).

### 2. Fan-Out / Smurfing
*   **Logic**: Detects single accounts dispersing funds to multiple recipients within a short time window.
*   **Behavior**: Characteristic of "placement" or "layering" stages where a mule herder distributes illicit funds.

### 3. High-Volume / Payroll Mules
*   **Logic**: Flags accounts with excessive flow-through (High In/High Out) but low retention, mimicking shell company behavior.

### 4. Vercel Serverless Optimizations
*   **Sampling**: Caps analysis at 10,000 rows to prevent Memory OOM (128MB limit).
*   **Timeouts**: Enforces a strict 5-second limit on cycle detection algorithms (O(n!)) to prevent HTTP 504 errors.
*   **Streamlined**: Single-file architecture (`api/index.py`) to eliminate cold-start import overhead.

---

## 🛠️ Tech Stack & Deployment

*   **Backend**: Python 3.9+, Flask, NetworkX, Pandas, Numpy.
*   **Frontend**: Vanilla HTML5, TailwindCSS, Cytoscape.js.
*   **Deployment**: Vercel (Monorepo: Frontend @ Root, Backend @ `/api`).

## 🚀 Deployment (Railway)

1.  **Push to GitHub**:
    ```bash
    git push origin main
    ```
2.  **Connect Railway**:
    *   New Project -> Deploy from Repo -> Select `rift-mule-detector`.
    *   Railway will detect `Procfile` and `requirements.txt`.
    *   It will build a container with Python + Pandas + NetworkX.
3.  **Live URL**: Railway will provide a `*.up.railway.app` URL.

**(Deprecated Vercel Instructions Removed)**

---

*Winner of the RIFT 2026 "Best Architecture" Category (Hypothetically).*
