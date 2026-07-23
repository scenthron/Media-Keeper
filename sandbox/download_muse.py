import urllib.request
import json
import os

print("Downloading MUSE dictionary from Facebook AI...")
url = "https://dl.fbaipublicfiles.com/arrival/dictionaries/ru-en.txt"
req = urllib.request.Request(url)
data = urllib.request.urlopen(req).read().decode('utf-8')

ru_en_dict = {}
lines = data.strip().split('\n')
for line in lines:
    parts = line.split(maxsplit=1)
    if len(parts) == 2:
        ru_word, en_word = parts
        # If the word is already mapped, skip, since the first occurrence is usually the most common translation in MUSE
        if ru_word not in ru_en_dict:
            ru_en_dict[ru_word] = en_word

print(f"Parsed {len(ru_en_dict)} unique Russian words.")

dict_dir = os.path.join("src", ".mediakeeper", "models", "dict")
os.makedirs(dict_dir, exist_ok=True)
dict_path = os.path.join(dict_dir, "ru_en_dict.json")

with open(dict_path, "w", encoding="utf-8") as f:
    json.dump(ru_en_dict, f, ensure_ascii=False, indent=2)

print(f"Saved to {dict_path} (File size: {os.path.getsize(dict_path) / 1024 / 1024:.2f} MB)")
