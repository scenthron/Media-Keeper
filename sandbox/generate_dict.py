import nltk
import json
import os

nltk.download('wordnet')
nltk.download('omw-1.4')
nltk.download('omw-2.0')
from nltk.corpus import wordnet as wn

ru_en_dict = {}

# OMW maps synsets across languages.
for synset in list(wn.all_synsets()):
    try:
        ru_lemmas = synset.lemma_names('rus')
        en_lemmas = synset.lemma_names('eng')
        
        if ru_lemmas and en_lemmas:
            primary_en = en_lemmas[0].replace('_', ' ')
            for ru_lemma in ru_lemmas:
                ru_word = ru_lemma.replace('_', ' ').lower()
                if ru_word not in ru_en_dict:
                    ru_en_dict[ru_word] = primary_en
    except Exception:
        pass

print(f"Generated dictionary with {len(ru_en_dict)} words.")

dict_dir = os.path.join("src", ".mediakeeper", "models", "dict")
os.makedirs(dict_dir, exist_ok=True)
dict_path = os.path.join(dict_dir, "ru_en_dict.json")

with open(dict_path, "w", encoding="utf-8") as f:
    json.dump(ru_en_dict, f, ensure_ascii=False, indent=2)

print(f"Dictionary saved to {dict_path}")
