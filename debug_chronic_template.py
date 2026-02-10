import sqlite3
import json

conn = sqlite3.connect('app.db')
cursor = conn.cursor()

cursor.execute('''
    SELECT cp.id, cp.full_name, cp.chronic_json, cp.record_kind 
    FROM clinic_patients cp 
    WHERE cp.record_kind="visit" 
    ORDER BY cp.id DESC 
    LIMIT 5;
''')

rows = cursor.fetchall()

print('=== Database Query Results ===')
for row in rows:
    print(f'ID: {row[0]}')
    print(f'Name: {row[1]}')
    print(f'Record Kind: {row[3]}')
    print(f'Raw Chronic JSON: {repr(row[2])}')
    
    # Try to parse the JSON
    if row[2]:
        try:
            if isinstance(row[2], str) and row[2].strip():
                parsed = json.loads(row[2])
                print(f'Parsed Chronic Data: {parsed}')
                print(f'Type: {type(parsed)}')
                
                # Check if it's a list
                if isinstance(parsed, list):
                    print(f'List contents: {parsed}')
                    print(f'Join result: {", ".join(parsed)}')
                else:
                    print(f'Not a list: {parsed}')
            else:
                print('Empty string or not string')
        except json.JSONDecodeError as e:
            print(f'JSON Parse Error: {e}')
    else:
        print('No chronic data (None or empty)')
    print('---')

# Now let's check what the template would see
print('\n=== Template Logic Test ===')
for row in rows:
    chronic_data = row[2]
    print(f'Processing for {row[1]} (ID: {row[0]})')
    print(f'Raw data: {repr(chronic_data)}')
    
    # Simulate the template logic
    if chronic_data:
        try:
            if isinstance(chronic_data, str) and chronic_data.strip():
                parsed_data = json.loads(chronic_data)
                print(f'After JSON parsing: {repr(parsed_data)}')
                
                # Template check: {% if visit.chronic_json is iterable and visit.chronic_json is not string %}
                if hasattr(parsed_data, '__iter__') and not isinstance(parsed_data, str):
                    print(f'✓ Template would show: {", ".join(parsed_data)}')
                else:
                    print(f'✗ Template would show: {parsed_data} (not iterable or is string)')
            else:
                print('Empty string case')
        except (json.JSONDecodeError, Exception) as e:
            print(f'Parse error: {e}')
    else:
        print('✗ Template would show: لا يوجد')
    print('---')

conn.close()