import sys
import os

filepath_logic = r"C:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\logic_ai.py"
with open(filepath_logic, "r", encoding="utf-8") as f:
    content = f.read()

import re

# Add translate_offline function
new_func = """
def translate_offline(query: str) -> str:
    \"\"\"Переводит слова в запросе по локальному словарю.\"\"\"
    import os, json
    from logic_paths import get_app_data_dir
    dict_path = os.path.join(get_app_data_dir(), "ai_dict.json")
    
    # Дефолтный словарь
    default_dict = {
        "хомяк": "hamster", "собака": "dog", "кошка": "cat", "кот": "cat",
        "машина": "car", "автомобиль": "car", "человек": "person",
        "дерево": "tree", "небо": "sky", "вода": "water", "море": "sea",
        "океан": "ocean", "птица": "bird", "рыба": "fish", "дом": "house",
        "здание": "building", "цветок": "flower", "солнце": "sun",
        "закат": "sunset", "рассвет": "sunrise", "гора": "mountain",
        "лес": "forest", "снег": "snow", "дождь": "rain", "облако": "cloud",
        "ночь": "night", "день": "day", "лицо": "face", "глаз": "eye",
        "улыбка": "smile", "девушка": "girl", "парень": "boy", "ребенок": "child",
        "мужчина": "man", "женщина": "woman", "еда": "food", "книга": "book",
        "оружие": "weapon", "телефон": "phone", "компьютер": "computer"
    }
    
    local_dict = default_dict.copy()
    if os.path.exists(dict_path):
        try:
            with open(dict_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
                local_dict.update(saved)
        except Exception:
            pass
    else:
        try:
            with open(dict_path, "w", encoding="utf-8") as f:
                json.dump(local_dict, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

    import string
    
    # Разбиваем по словам (с сохранением разделителей) и переводим
    words = query.split()
    translated = []
    for w in words:
        # Убираем знаки препинания по краям для поиска в словаре
        clean_w = w.strip(string.punctuation).lower()
        if clean_w in local_dict:
            # Заменяем слово, но пытаемся сохранить регистр? Для CLIP пофиг, он lowercase.
            translated.append(local_dict[clean_w])
        else:
            translated.append(w)
            
    return " ".join(translated)

"""

if "def translate_offline" not in content:
    content = content.replace("class AiEngine:", new_func + "class AiEngine:")

# Update extract_text_embedding
old_extract = """    def extract_text_embedding(self, text: str) -> np.ndarray | None:
        \"\"\"Возвращает CLIP-вектор текста (512-d).\"\"\"
        if not self._is_initialized:
            return None
            
        try:
            from deep_translator import GoogleTranslator
            # Переводим текст на английский, так как наша модель CLIP лучше всего понимает английский
            translated_text = GoogleTranslator(source='auto', target='en').translate(text)
            if translated_text:
                import logging
                logging.info(f"Переведен поисковый запрос: '{text}' -> '{translated_text}'")
                text = translated_text
        except Exception as e:
            import logging
            logging.error(f"Ошибка перевода текста: {e}")
            
        return self.clip_searcher.encode_text(text)"""

new_extract = """    def extract_text_embedding(self, text: str) -> np.ndarray | None:
        \"\"\"Возвращает CLIP-вектор текста (512-d).\"\"\"
        if not self._is_initialized:
            return None
            
        # Локальный оффлайн перевод
        translated_text = translate_offline(text)
        if translated_text != text:
            import logging
            logging.info(f"Оффлайн перевод запроса: '{text}' -> '{translated_text}'")
            text = translated_text
            
        return self.clip_searcher.encode_text(text)"""

content = content.replace(old_extract, new_extract)

with open(filepath_logic, "w", encoding="utf-8") as f:
    f.write(content)
print("logic_ai patched")
