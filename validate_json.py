import json
try:
    with open('bot/locales/en.json', 'r') as f:
        json.load(f)
    print("JSON VALID")
except Exception as e:
    print(f"JSON INVALID: {e}")
