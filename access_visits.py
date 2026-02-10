import requests
import time

print("Accessing visits page...")

try:

    response = requests.get("http://localhost:8000/clinic/visits", timeout=10)
    print(f"Status: {response.status_code}")
    print(f"Response length: {len(response.text)}")
    

    if "CHRONIC DISEASE DEBUG" in response.text:
        print("FOUND DEBUG OUTPUT!")
        lines = response.text.split('\n')
        for i, line in enumerate(lines):
            if 'CHRONIC DISEASE DEBUG' in line:

                print(f"Line {i}: {line.strip()}")
                for j in range(i, min(len(lines), i+20)):
                    if j != i:
                        print(f"  {lines[j].strip()}")
                        if '===========================' in lines[j]:
                            break
                break
    

    if "chronic-diseases" in response.text:
        print("\nFound chronic-diseases class in HTML")

        lines = response.text.split('\n')
        in_table = False
        for i, line in enumerate(lines):
            if '<tbody>' in line:
                in_table = True
            elif '</tbody>' in line:
                in_table = False
            elif in_table and 'chronic-diseases' in line:
                print(f"Chronic disease cell found at line {i}:")

                for j in range(max(0, i-3), min(len(lines), i+4)):
                    print(f"  {j}: {lines[j].strip()}")
                print("---")
    

    if "login" in response.text.lower():
        print("Login page detected - authentication required")
    else:
        print("Not a login page - should be visits list")
        
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()