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
