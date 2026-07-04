import os

# Fix ui_ai_group_dialog.py
dialog_path = 'src/modules/cleaner/ui_ai_group_dialog.py'
with open(dialog_path, 'r', encoding='utf-8') as f:
    dialog_content = f.read()

dialog_old = '''    def _on_item_hover(self, item, global_pos):
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):'''
dialog_new = '''    def _on_item_hover(self, path, global_pos):
        if not path or not os.path.exists(path):'''
dialog_content = dialog_content.replace(dialog_old, dialog_new)

dialog_lbl_old = '''                    self.hover_tooltip.lbl_image.setPixmap(pixmap)
                    self.hover_tooltip.move(global_pos)
                    self.hover_tooltip.show()
                    return
            except Exception as e:
                logging.error(f"Error drawing bbox: {e}")
                
        self.hover_tooltip.show_image(item, global_pos)'''
dialog_lbl_new = '''                    self.hover_tooltip.setPixmap(pixmap)
                    self.hover_tooltip.move(global_pos)
                    self.hover_tooltip.show()
                    return
            except Exception as e:
                logging.error(f"Error drawing bbox: {e}")
                
        self.hover_tooltip.show_image(path, global_pos)'''
dialog_content = dialog_content.replace(dialog_lbl_old, dialog_lbl_new)

with open(dialog_path, 'w', encoding='utf-8') as f:
    f.write(dialog_content)


# Fix ui_widgets.py
widgets_path = 'src/modules/cleaner/ui_widgets.py'
with open(widgets_path, 'r', encoding='utf-8') as f:
    widgets_content = f.read()

init_old = '''        self.delegate = RefImageDelegate(self)
        self.setItemDelegate(self.delegate)
        
    def dragEnterEvent(self, event):'''
init_new = '''        self.delegate = RefImageDelegate(self)
        self.setItemDelegate(self.delegate)
        
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(500)
        self.hover_timer.timeout.connect(self._emit_hover)
        self._pending_hover_path = None
        self._pending_hover_pos = None

    def _emit_hover(self):
        if self._pending_hover_path:
            self.item_hovered.emit(self._pending_hover_path, self._pending_hover_pos)
            
    def dragEnterEvent(self, event):'''
widgets_content = widgets_content.replace(init_old, init_new)

mouse_old = '''        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                glob_pos = self.mapToGlobal(event.pos())
                self.item_hovered.emit(path, glob_pos)
        else:
            self.hover_left.emit()

    def leaveEvent(self, event):'''
mouse_new = '''        if item:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                glob_pos = self.mapToGlobal(event.pos())
                if path != self._pending_hover_path:
                    self._pending_hover_path = path
                    self._pending_hover_pos = glob_pos
                    self.hover_timer.start()
                else:
                    # Update position in case it changed slightly, but don't restart timer
                    self._pending_hover_pos = glob_pos
        else:
            self._pending_hover_path = None
            self.hover_timer.stop()
            self.hover_left.emit()

    def leaveEvent(self, event):'''
widgets_content = widgets_content.replace(mouse_old, mouse_new)

leave_old = '''    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.delegate.hovered_index is not None:
            self.delegate.hovered_index = None
            self.viewport().update()'''
leave_new = '''    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self.delegate.hovered_index is not None:
            self.delegate.hovered_index = None
            self.viewport().update()
        self.hover_timer.stop()
        self._pending_hover_path = None
        self.hover_left.emit()'''
widgets_content = widgets_content.replace(leave_old, leave_new)

with open(widgets_path, 'w', encoding='utf-8') as f:
    f.write(widgets_content)

print('Applied')
