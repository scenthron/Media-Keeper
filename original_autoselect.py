    def update_autoselect_items(self):
        self.combo_autoselect.clear()
        def add_item(text, tooltip, index_val):
            self.combo_autoselect.addItem(text, index_val)
            self.combo_autoselect.setItemData(self.combo_autoselect.count() - 1, tooltip, Qt.ItemDataRole.ToolTipRole)
        def add_sep():
            self.combo_autoselect.addItem("", "separator")
            idx = self.combo_autoselect.count() - 1
            self.combo_autoselect.model().item(idx).setEnabled(False)
            self.combo_autoselect.setItemData(idx, QSize(0, 9), Qt.ItemDataRole.SizeHintRole)

        is_similar = getattr(self, 'is_similar_mode', False)
        is_ru = (AppContext.LANG == "RU")

        if is_similar:
            add_item("Автовыбор" if is_ru else "Autoselect", "Выберите условие автоматического выделения" if is_ru else "Choose autoselect condition", 0)
            add_sep()
            add_item("Оставить больший размер" if is_ru else "Keep largest size", 
                     "Выделить все файлы в группе, кроме файла с наибольшим размером" if is_ru else "Mark all files except the one with largest size", 2)
            add_item("Оставить меньший размер" if is_ru else "Keep smallest size", 
                     "Выделить все файлы в группе, кроме файла с наименьшим размером" if is_ru else "Mark all files except the one with smallest size", 3)
            add_sep()
            add_item("Оставить самый новый" if is_ru else "Keep newest", 
                     "Выделить все файлы в группе, кроме самого свежего по дате" if is_ru else "Mark all files except the newest one", 8)
            add_item("Оставить самый старый" if is_ru else "Keep oldest", 
                     "Выделить все файлы в группе, кроме самого старого по дате" if is_ru else "Mark all files except the oldest one", 9)
        else:
            add_item(AppContext.tr("cln_sel_auto"), AppContext.tr("cln_sel_tip_none"), 0)
            add_sep()
            add_item(AppContext.tr("cln_sel_all_except_first"), AppContext.tr("cln_sel_tip_except_first"), 2)
            add_item(AppContext.tr("cln_sel_all_except_last"), AppContext.tr("cln_sel_tip_except_last"), 3)
            add_sep()
            add_item(AppContext.tr("cln_sel_shortest"), AppContext.tr("cln_sel_tip_shortest"), 5)
            add_item(AppContext.tr("cln_sel_longest"), AppContext.tr("cln_sel_tip_longest"), 6)
            add_sep()
            add_item(AppContext.tr("cln_sel_newest"), AppContext.tr("cln_sel_tip_newest"), 8)
            add_item(AppContext.tr("cln_sel_oldest"), AppContext.tr("cln_sel_tip_oldest"), 9)
            add_sep()
            add_item(AppContext.tr("cln_sel_shallow"), AppContext.tr("cln_sel_tip_shallow"), 11)
            add_item(AppContext.tr("cln_sel_deep"), AppContext.tr("cln_sel_tip_deep"), 12)
            add_sep()
            add_item(AppContext.tr("cln_sel_protected_dupes"), AppContext.tr("cln_sel_tip_protected_dupes"), 14)
            add_item(AppContext.tr("cln_sel_reference_dupes"), AppContext.tr("cln_sel_tip_reference_dupes"), 15)

