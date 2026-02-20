# Project Name
Mule Watch - Fraud Detection 

## Problem Statement
Money muling is a critical component of financial crime where criminals use networks of individuals ("mules") to transfer and layer illicit funds through multiple accounts.
Traditional database queries fail to detect these sophisticated multi - hop networks. 

## Our Solution
- We developed a web-based Financial Forensics Engine that:
- Converts transaction CSV data into a directed graph
- Applies graph algorithms to detect fraud rings
- Identifies cycles, smurfing patterns, and shell networks
- Calculates suspicion scores (0–100)
- Generates downloadable JSON output in exact required format
- Visually highlights suspicious accounts in an interactive graph
Our approach uses graph theory + temporal analysis + heuristic risk scoring to achieve high precision while minimizing false positives.

## Features (MWP)
- CSV Upload (exact format validation)
- Interactive Graph Visualization (Directed Graph)
- Cycle Detection (length 3–5)
- Smurfing Detection (Fan-in / Fan-out within 72 hrs)
- Shell Account Layer Detection
- Suspicion Score Calculation (0–100 scale)
- Downloadable JSON Output (Exact required format)
- Fraud Ring Summary Table (UI Display)
- Processing time under 30 seconds (≤10K transactions)

## Tech Stack
- Frontend: HTML 
- Backend: Python 

## System Architecture
CSV Upload
     ↓
Backend Validation
     ↓
Graph Construction (Directed)
     ↓
Pattern Detection Engine
     ├── Cycle Detection (DFS)
     ├── Smurfing Detection (Temporal grouping)
     ├── Shell Network Detection (Low-degree chain analysis)
     ↓
Suspicion Score Engine
     ↓
JSON Output Generator
     ↓
Frontend Graph + Summary Table

## How it Works
Step 1: Open live deployed link

Step 2: Upload CSV file (exact required format)

Step 3: Click "Analyze Transactions"
        View:
            Interactive graph
            Fraud ring summary table

Step 4: Click "Download JSON Report"


## Demo
- Video Link:
- Live Link (if any):

## Future Scope
- Machine Learning anomaly detection layer
- Community detection (Louvain method)
- Real-time monitoring dashboard
- Risk heatmap visualization
- API integration for banks

## Team Members
Lokesh Uike – Backend & Graph Algorithms

Premnath Sonkusre – Frontend + UI/UX

Samiksha Hedau - Visualization

Danish Siddiqui – Frontend + Testing & Documentation
