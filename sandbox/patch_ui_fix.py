import sys

with open('src/modules/cleaner/ui_ai_tab.py', 'r', encoding='utf-8') as f:
    code = f.read()

code = code.replace(
    'matched_bbox = user_data.get("matched_bbox") if user_data else None',
    'matched_bbox = data.get("matched_bbox") if data else None'
)

with open('src/modules/cleaner/ui_ai_tab.py', 'w', encoding='utf-8') as f:
    f.write(code)
print("Replaced!")
