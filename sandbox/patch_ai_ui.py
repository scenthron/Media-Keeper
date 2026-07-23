import re
import os

with open("c:/Users/Centhron/Desktop/Media_Keeper/src/modules/cleaner/ui_ai_lab.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Insert FolderDropButton
folder_btn_code = """
class FolderDropButton(QPushButton):
    def __init__(self, text, drop_callback, parent=None):
        super().__init__(text, parent)
        self.drop_callback = drop_callback
        self.setAcceptDrops(True)
        
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile() and os.path.isdir(url.toLocalFile()):
                    event.acceptProposedAction()
                    return
        event.ignore()
        
    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if os.path.isdir(path):
                    self.drop_callback(path)
                    return

class AILabTab(QWidget):
"""
content = content.replace("class AILabTab(QWidget):", folder_btn_code)

# 2. Use FolderDropButton
content = content.replace('self.btn_select_folder = QPushButton("Выбрать папку" if self.is_ru else "Select Folder")',
                          'self.btn_select_folder = FolderDropButton("Выбрать папку" if self.is_ru else "Select Folder", self.set_selected_folder)')

# 3. Add set_selected_folder
set_folder_code = """    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для поиска" if self.is_ru else "Select Folder to Search")
        if folder:
            self.set_selected_folder(folder)

    def set_selected_folder(self, folder):
        self.selected_folder = folder
        self.lbl_selected_folder.setText(folder)"""
old_select_folder = """    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку для поиска" if self.is_ru else "Select Folder to Search")
        if folder:
            self.selected_folder = folder
            self.lbl_selected_folder.setText(folder)"""
content = content.replace(old_select_folder, set_folder_code)

# 4. Add UserRole to items
content = content.replace("self.results_list.addItem(item)\n                self.results_list.setItemWidget(item, tile)",
                          "item.setData(Qt.ItemDataRole.UserRole, file_path)\n                self.results_list.addItem(item)\n                self.results_list.setItemWidget(item, tile)")

# 5. Connect double click
content = content.replace("self.results_list.setSpacing(10)",
                          "self.results_list.setSpacing(10)\n        self.results_list.itemDoubleClicked.connect(self.on_item_double_clicked)")

# 6. Add on_item_double_clicked
double_click_code = """    def on_item_double_clicked(self, item):
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            os.startfile(path)

    def on_btn_search_clicked(self):"""
content = content.replace("    def on_btn_search_clicked(self):", double_click_code)

# 7. Nullify self.worker
finished_code = """    def on_search_finished(self):
        self.worker = None
        self.progress_bar.hide()
        self.reset_search_button()
        self.render_results()"""
old_finished = """    def on_search_finished(self):
        self.progress_bar.hide()
        self.reset_search_button()
        self.render_results()"""
content = content.replace(old_finished, finished_code)

error_code = """    def on_search_error(self, err_msg):
        self.worker = None
        self.progress_bar.hide()
        self.reset_search_button()"""
old_error = """    def on_search_error(self, err_msg):
        self.progress_bar.hide()
        self.reset_search_button()"""
content = content.replace(old_error, error_code)

with open("c:/Users/Centhron/Desktop/Media_Keeper/src/modules/cleaner/ui_ai_lab.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Patch applied.")
