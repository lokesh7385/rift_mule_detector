# Money Mule Detection Engine — Project Walkthrough

## 🚀 Overview
The **Money Mule Detection Engine** is a specialized forensic tool designed to identify complex financial fraud patterns within transaction datasets. It uses graph algorithms to detect money laundering structures such as **Cycles** (Round-Tripping), **Smurfing** (Fan-In/Fan-Out), and **Layered Shell Networks**.

## ✨ Key Features
1.  **Advanced Fraud Detection**:
    *   **Cycles**: Detects closed loops of 3–5 accounts (e.g., A → B → C → A).
    *   **Smurfing**: Identifies "Fan-Out" (one source -> many mules) and "Fan-In" (many mules -> one collector).
    *   **Layering**: Flags chains of shell accounts used to distance illicit funds from their source.
2.  **Interactive Visualization**:
    *   Force-directed graph (Cytoscape-style logic) with fraud rings highlighted in **Red**.
    *   "Drifting" animation for inactive nodes, high-velocity particle effects for fraud edges.
3.  **Detailed Forensics**:
    *   **Risk Scoring**: Accounts are scored (0-100) based on participation in fraud patterns.
    *   **Ring Details**: Click "View" to see exact transaction counts, confidence scores, and pattern interactions.
4.  **Production Ready**:
    *   Includes `Procfile` and `render.yaml` for immediate deployment.
    *   Clean, dependency-locked `requirements.txt`.

## 🛠️ How to Run Locally

### Prerequisites
*   Python 3.11+
*   Pip

### Steps
1.  **Clone/Open the Repository**
2.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Start the Backend**:
    ```bash
    python backend/app.py
    ```
4.  **Access the UI**:
    Open your browser to `http://127.0.0.1:5001`.

## 🧪 Verification Results

We have rigorously tested the engine against multiple datasets:

### 1. Local Dataset (`dataset/money-mulling.csv`)
*   **Status**: ✅ Verified
*   **Findings**:
    *   **5 Fraud Rings** detected total.
    *   **3 Cycles**: Typical round-tripping behavior.
    *   **2 Smurfing (Fan-In)** rings: `SMURF_01` and `MERCHANT_01` (flagged for high variance).

### 2. Synthetic Stress Test
*   **Status**: ✅ Verified
*   **Findings**:
    *   Generated specific "Layering" and "Spoofing" scenarios.
    *   Engine correctly identified **Shell Networks** (Layering) and **Fan-Out** patterns.

## 📂 Project Structure
*   `backend/app.py`: Main Flask application.
*   `backend/graph_engine.py`: Core logic for graph construction and fraud algorithms.
*   `backend/static/`: Frontend assets (HTML, polished CSS, interactive JS).
*   `requirements.txt`: Pinned production dependencies.

## 🚢 Deployment
The project is configured for **Render** or **Heroku**.
*   **Entry Point**: `gunicorn app:app --chdir backend`
*   **Config**: See `render.yaml`.

---
*Built with ❤️ for the Hackathon.*
