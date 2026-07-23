import sys
sys.path.append('src')
from modules.cleaner.logic_clip import CLIPSearcher
import numpy as np

clip = CLIPSearcher()

if clip.is_loaded:
    emb_ru = clip.encode_text("хомяк")
    emb_en = clip.encode_text("hamster")
    print("Sim(хомяк, hamster):", clip.compute_similarity(emb_ru, emb_en))
    
    emb_dog_ru = clip.encode_text("собака")
    print("Sim(хомяк, собака):", clip.compute_similarity(emb_ru, emb_dog_ru))
    print("Sim(hamster, собака):", clip.compute_similarity(emb_en, emb_dog_ru))
else:
    print("Not loaded")
