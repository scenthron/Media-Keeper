import os
import json
import logging
from .logic_ai_classifier import get_ai_assets_dir

class AiTextTagsManager:
    def __init__(self):
        self.tags_file = os.path.join(get_ai_assets_dir(), "ai_text_tags.json")
        self.tags = self.load_tags()

    def load_tags(self) -> dict:
        if not os.path.exists(self.tags_file):
            return {}
        try:
            with open(self.tags_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("tags", {})
        except Exception as e:
            logging.error(f"Error loading text tags: {e}")
            return {}

    def save_tags(self):
        try:
            with open(self.tags_file, "w", encoding="utf-8") as f:
                json.dump({"tags": self.tags}, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Error saving text tags: {e}")

    def get_tags(self) -> dict:
        return self.tags

    def tag_exists(self, name: str) -> bool:
        return name in self.tags

    def add_or_update_tag(self, name: str, body: str):
        self.tags[name] = body
        self.save_tags()

    def delete_tag(self, name: str):
        if name in self.tags:
            del self.tags[name]
            self.save_tags()

import re
from PyQt6.QtGui import QFont, QColor, QSyntaxHighlighter, QTextCharFormat

def parse_multi_tags(text: str) -> dict:
    result = {}
    group_counter = 1
    
    # 1. Match named groups [Name: t1, t2]
    pattern_named = r'\[([^:\]]+):([^\]]+)\]'
    for match in re.finditer(pattern_named, text):
        group_name = match.group(1).strip()
        components = [c.strip() for c in match.group(2).split(',') if c.strip()]
        if components:
            result[group_name] = components
            
    text_clean = re.sub(pattern_named, '', text)
    
    # 2. Match unnamed groups [t1, t2]
    pattern_unnamed = r'\[([^\]]+)\]'
    for match in re.finditer(pattern_unnamed, text_clean):
        components = [c.strip() for c in match.group(1).split(',') if c.strip()]
        if components:
            result[f"Группа {group_counter}"] = components
            group_counter += 1
            
    text_clean = re.sub(pattern_unnamed, '', text_clean)
    
    # 3. Everything else outside parens is ONE group!
    components = [c.strip() for c in text_clean.split(',') if c.strip()]
    if components:
        result[f"Группа {group_counter}"] = components
        
    return result

def parse_tag_weight(tag_text: str) -> dict:
    """Извлекает слово и вес из строки вида 'собака(80)'. Если веса нет, возвращает None."""
    import re
    match = re.search(r'^(.*?)\((\d+)\)$', tag_text.strip())
    if match:
        word = match.group(1).strip()
        try:
            weight = float(match.group(2))
            return {"text": word, "weight": weight}
        except ValueError:
            return {"text": word, "weight": None}
    return {"text": tag_text.strip(), "weight": None}

class MultiTagHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)

    def highlightBlock(self, text):
        # 1. По умолчанию всё зеленое (позитивные паттерны и их веса)
        self.setFormat(0, len(text), QColor("#10b981"))
        
        # 2. Серые запятые
        for match in re.finditer(r',', text):
            self.setFormat(match.start(), match.end() - match.start(), QColor("#888888"))
            
        # 3. Красные антипаттерны (включая скобки с весом, до запятой или закрывающей скобки группы)
        for match in re.finditer(r'-\s*[^,\[\]]+', text):
            self.setFormat(match.start(), match.end() - match.start(), QColor("#ef4444"))
            
        # 4. Оранжевые группы (открывающая скобка с именем [Name: и закрывающая скобка ])
        for match in re.finditer(r'\[[^:\]]+:|\]', text):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor("#f59e0b"))
            fmt.setFontWeight(QFont.Weight.Bold)
            self.setFormat(match.start(), match.end() - match.start(), fmt)

