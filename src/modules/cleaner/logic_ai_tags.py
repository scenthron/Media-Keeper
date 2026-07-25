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
    
    # 1. Match named groups (Name: t1, t2)
    pattern_named = r'\(([^:\)]+):([^\)]+)\)'
    for match in re.finditer(pattern_named, text):
        group_name = match.group(1).strip()
        components = [c.strip() for c in match.group(2).split(',') if c.strip()]
        if components:
            result[group_name] = components
            
    text_clean = re.sub(pattern_named, '', text)
    
    # 2. Match unnamed groups (t1, t2)
    pattern_unnamed = r'\(([^\)]+)\)'
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

class MultiTagHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.rules = []

        format_components = QTextCharFormat()
        format_components.setForeground(QColor("#ffffff"))

        format_group = QTextCharFormat()
        format_group.setForeground(QColor("#f59e0b"))
        format_group.setFontWeight(QFont.Weight.Bold)

        format_normal = QTextCharFormat()
        format_normal.setForeground(QColor("#10b981"))
        
        format_punct = QTextCharFormat()
        format_punct.setForeground(QColor("#888888"))

        self.rules.append((re.compile(r'[\(\):,]'), format_punct))

    def highlightBlock(self, text):
        self.setFormat(0, len(text), QColor("#10b981"))
        pattern = re.compile(r'\((.*?)\)')
        for match in pattern.finditer(text):
            start = match.start()
            length = match.end() - start
            inner_text = match.group(1)
            
            self.setFormat(start + 1, length - 2, QColor("#ffffff"))
            
            colon_idx = inner_text.find(':')
            if colon_idx != -1:
                self.setFormat(start + 1, colon_idx, QColor("#f59e0b"))
                fmt = QTextCharFormat()
                fmt.setForeground(QColor("#f59e0b"))
                fmt.setFontWeight(QFont.Weight.Bold)
                self.setFormat(start + 1, colon_idx, fmt)

        punct_pattern = re.compile(r'[\(\):,]')
        for match in punct_pattern.finditer(text):
            self.setFormat(match.start(), 1, QColor("#888888"))
            
        neg_pattern = re.compile(r'-\s*[^,\)]+')
        for match in neg_pattern.finditer(text):
            self.setFormat(match.start(), match.end() - match.start(), QColor("#ef4444"))

