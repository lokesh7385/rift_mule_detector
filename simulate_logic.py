import sys
import os
import io
import json

# Ensure we can import from api folder
sys.path.append(os.getcwd())

# Ensure we can import from api folder
sys.path.append(os.getcwd())

try:
    from api.index import analyze
    print("[OK] Successfully imported 'analyze' from api.index")
except ImportError as e:
    print(f"[ERROR] ImportError: {e}")
    sys.exit(1)

def run_simulation():
    # 1. Create Dummy CSV (Cycle Pattern + Fan Out)
    csv_content = """sender_id,receiver_id,amount,timestamp
A,B,1000,2023-01-01T10:00:00Z
B,C,1000,2023-01-01T11:00:00Z
C,A,1000,2023-01-01T12:00:00Z
Mule_Hub,Mule_1,500,2023-01-02T10:00:00Z
Mule_Hub,Mule_2,500,2023-01-02T10:00:00Z
Mule_Hub,Mule_3,500,2023-01-02T10:00:00Z
"""
    print("running simulation with dummy data...")
    file_obj = io.StringIO(csv_content)
    
    # 2. Run Analysis
    try:
        result = analyze(file_obj)
    except Exception as e:
        print(f"[ERROR] Analysis Failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # 3. Validation Logic
    print("\n[INFO] Validating Output Schema...")
    
    # Check Top Level Keys
    required_keys = {'suspicious_accounts', 'fraud_rings', 'summary'}
    if not required_keys.issubset(result.keys()):
        print(f"[ERROR] Missing keys. Found: {list(result.keys())}")
        sys.exit(1)
    
    # Check Float Casting
    suspicious = result['suspicious_accounts']
    if suspicious:
        score = suspicious[0]['suspicion_score']
        if not isinstance(score, float):
            print(f"[ERROR] Suspicion Score is not float: {type(score)} ({score})")
            sys.exit(1)
        else:
            print(f"[OK] Suspicion Score is float: {score}")

    rings = result['fraud_rings']
    cycle_found = False
    for r in rings:
        if r['pattern_type'] == 'cycle':
            cycle_found = True
            if not isinstance(r['risk_score'], float):
                print(f"[ERROR] Ring Risk Score is not float: {type(r['risk_score'])}")
                sys.exit(1)
    
    if cycle_found:
        print("[OK] Cycle detected successfully")
    else:
        print("[WARN] No cycle detected (Check logic)")

    print("\n[SUCCESS] Simulation Passed! JSON Output is valid.")
    # print(json.dumps(result, indent=2))

if __name__ == "__main__":
    run_simulation()
