import os
import json
import uuid
import time
import logging
from config import AppContext
from logic_paths import get_app_data_dir

JOURNAL_FILE = os.path.join(get_app_data_dir(), "move_journal.json")
MAX_JOURNAL_ENTRIES = 10

class MoveJournal:
    _instance = None
    
    @classmethod
    def inst(cls):
        if cls._instance is None:
            cls._instance = MoveJournal()
        return cls._instance

    def __init__(self):
        self.entries = []
        self._load()

    def _load(self):
        if os.path.exists(JOURNAL_FILE):
            try:
                with open(JOURNAL_FILE, 'r', encoding='utf-8') as f:
                    self.entries = json.load(f)
            except Exception as e:
                logging.error(f"Error loading move journal: {e}")
                self.entries = []
        else:
            self.entries = []

    def _save(self):
        try:
            with open(JOURNAL_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.entries, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Error saving move journal: {e}")

    def add_entry(self, pairs):
        """
        Добавляет новую запись о перемещении.
        pairs: список кортежей/списков [(dst, src), (dst2, src2), ...]
        """
        if not pairs:
            return
            
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "pairs": [{"dst": p[0], "src": p[1]} for p in pairs],
            "status": "valid" # 'valid', 'done'
        }
        
        # Вставляем в начало (самые новые сверху)
        self.entries.insert(0, entry)
        
        # Ограничиваем историю
        if len(self.entries) > MAX_JOURNAL_ENTRIES:
            self.entries = self.entries[:MAX_JOURNAL_ENTRIES]
            
        self._save()

    def mark_done(self, entry_id):
        """Отмечает запись как выполненную (откаченную)."""
        for entry in self.entries:
            if entry.get("id") == entry_id:
                entry["status"] = "done"
                break
        self._save()
        
    def clear(self):
        """Полностью очищает журнал."""
        self.entries = []
        self._save()
        
    def get_entries(self):
        return self.entries
