import sys
import os

filepath_ui = r"C:\Users\Centhron\Desktop\Media_Keeper\src\modules\cleaner\ui_ai_tab.py"
with open(filepath_ui, "r", encoding="utf-8") as f:
    content = f.read()

dialog_code = """
class AiDictDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Словарь ИИ (Оффлайн)" if AppContext.is_ru() else "AI Dict (Offline)")
        self.resize(400, 500)
        
        from logic_paths import get_app_data_dir
        self.dict_path = os.path.join(get_app_data_dir(), "ai_dict.json")
        self.local_dict = {}
        
        layout = QVBoxLayout(self)
        
        info = QLabel("Этот словарь автоматически переводит ваши русские слова в английские перед отправкой в нейросеть." if AppContext.is_ru() else "This dictionary automatically translates words to English before sending to AI.")
        info.setWordWrap(True)
        info.setStyleSheet("color: #ccc; font-size: 12px; margin-bottom: 10px;")
        layout.addWidget(info)
        
        # Поиск
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск..." if AppContext.is_ru() else "Search...")
        self.search_input.setStyleSheet("padding: 5px; background: #222; border: 1px solid #333; color: white;")
        layout.addWidget(self.search_input)
        
        self.table = QTableWidget()
        self.table.setColumnCount(2)
        self.table.setHorizontalHeaderLabels(["Слово (Рус)" if AppContext.is_ru() else "Word (Orig)", "Перевод (Англ)" if AppContext.is_ru() else "Translation (EN)"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.setStyleSheet("QTableWidget { background: #1e1e1e; color: white; border: 1px solid #333; } QHeaderView::section { background: #2d2d2d; color: white; padding: 4px; border: 1px solid #333; }")
        layout.addWidget(self.table)
        
        h_layout = QHBoxLayout()
        self.btn_add = QPushButton("Добавить" if AppContext.is_ru() else "Add")
        self.btn_del = QPushButton("Удалить" if AppContext.is_ru() else "Delete")
        self.btn_save = QPushButton("Сохранить" if AppContext.is_ru() else "Save")
        
        for b in [self.btn_add, self.btn_del, self.btn_save]:
            b.setStyleSheet("QPushButton { background-color: #3b82f6; color: white; border-radius: 4px; padding: 6px; } QPushButton:hover { background-color: #2563eb; }")
            h_layout.addWidget(b)
            
        layout.addLayout(h_layout)
        
        self.load_dict()
        self.populate_table()
        
        self.search_input.textChanged.connect(self.populate_table)
        self.btn_add.clicked.connect(self.add_row)
        self.btn_del.clicked.connect(self.del_row)
        self.btn_save.clicked.connect(self.save_dict)
        
    def load_dict(self):
        import json
        if os.path.exists(self.dict_path):
            try:
                with open(self.dict_path, "r", encoding="utf-8") as f:
                    self.local_dict = json.load(f)
            except Exception:
                pass
                
    def populate_table(self):
        self.table.setRowCount(0)
        q = self.search_input.text().lower()
        for k, v in self.local_dict.items():
            if q in k.lower() or q in v.lower():
                r = self.table.rowCount()
                self.table.insertRow(r)
                self.table.setItem(r, 0, QTableWidgetItem(k))
                self.table.setItem(r, 1, QTableWidgetItem(v))
                
    def add_row(self):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem("новое_слово"))
        self.table.setItem(r, 1, QTableWidgetItem("new_word"))
        self.table.scrollToBottom()
        
    def del_row(self):
        r = self.table.currentRow()
        if r >= 0:
            self.table.removeRow(r)
            
    def save_dict(self):
        new_dict = {}
        for r in range(self.table.rowCount()):
            k_item = self.table.item(r, 0)
            v_item = self.table.item(r, 1)
            if k_item and v_item:
                k = k_item.text().strip().lower()
                v = v_item.text().strip().lower()
                if k and v:
                    new_dict[k] = v
        
        import json
        try:
            with open(self.dict_path, "w", encoding="utf-8") as f:
                json.dump(new_dict, f, ensure_ascii=False, indent=4)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Успех" if AppContext.is_ru() else "Success", "Словарь сохранен!" if AppContext.is_ru() else "Dictionary saved!")
            self.local_dict = new_dict
        except Exception as e:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "Ошибка" if AppContext.is_ru() else "Error", str(e))
"""

if "class AiDictDialog" not in content:
    content = content.replace("class AiClassificationTab(QWidget):", dialog_code + "\nclass AiClassificationTab(QWidget):")

# Button insertion
insert_marker = """        params_sub_layout.addWidget(self.lbl_threshold)"""
button_code = """        
        # Кнопка словаря
        self.btn_dict = QPushButton("Словарь" if AppContext.is_ru() else "Dict")
        self.btn_dict.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_dict.setStyleSheet("QPushButton { background-color: #4b5563; color: white; border-radius: 4px; padding: 2px 6px; font-size: 11px; } QPushButton:hover { background-color: #374151; }")
        self.btn_dict.clicked.connect(self.open_dict_dialog)
        
        thresh_header_layout = QHBoxLayout()
        thresh_header_layout.addWidget(self.lbl_threshold)
        thresh_header_layout.addStretch()
        thresh_header_layout.addWidget(self.btn_dict)
        params_sub_layout.addLayout(thresh_header_layout)
"""

if "self.btn_dict = QPushButton" not in content:
    content = content.replace("        params_sub_layout.addWidget(self.lbl_threshold)", button_code)

open_dict_code = """
    def open_dict_dialog(self):
        dlg = AiDictDialog(self)
        dlg.exec()
"""

if "def open_dict_dialog" not in content:
    content = content.replace("    def start_text_search(self):", open_dict_code + "\n    def start_text_search(self):")

with open(filepath_ui, "w", encoding="utf-8") as f:
    f.write(content)
print("ui_ai_tab patched")
