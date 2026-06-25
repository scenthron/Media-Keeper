
import random
import re
import os
from PyQt6.QtWidgets import QFileIconProvider
from PyQt6.QtCore import QFileInfo, QSize
from PyQt6.QtGui import QIcon, QPixmap
from config import APP_DESIGN

def format_size(size_bytes):
    # Защита: если передано отрицательное число (результат переполнения или ошибки кэша)
    if size_bytes is None or size_bytes <= 0: return "0 B"
    
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    p = float(size_bytes)
    while p >= 1024 and i < len(units) - 1:
        p /= 1024
        i += 1
    
    # Force 2 decimal places for stability (e.g. 12.30 MB)
    return f"{p:.2f} {units[i]}"

def truncate_text(text, max_len=None):
    if max_len is None: max_len = APP_DESIGN['max_name_len']
    if len(text) > max_len:
        return text[:max_len-3] + "..."
    return text

def generate_random_bg_color():
    r = random.randint(10, 60)
    g = random.randint(10, 60)
    b = random.randint(10, 60)
    return f"#{r:02x}{g:02x}{b:02x}"

def get_folder_icon(path):
    """
    Returns a QIcon for the given path using the system's icon provider.
    Detects Drives, Network shares, etc.
    """
    provider = QFileIconProvider()
    norm_path = os.path.normpath(path)
    info = QFileInfo(norm_path)
    
    if os.name == 'nt' and len(norm_path) == 2 and norm_path[1] == ':':
        info = QFileInfo(norm_path + "\\")

    if os.path.exists(norm_path) or (os.name == 'nt' and len(norm_path) <= 3):
        icon = provider.icon(info)
    else:
        icon = provider.icon(QFileIconProvider.IconType.Folder)
    return icon

def markdown_to_html(md_text):
    """
    Markdown to HTML converter for Help dialog.
    Supports: # Headers, **Bold**, *Italic*, `code`, [link](url),
              - Unordered lists, 1. Ordered lists, --- Divider, | Tables |
    """
    if not md_text:
        return ""

    LINK_COLOR = "#89b4fa"

    def apply_inline(text):
        text = re.sub(r'\*\*(.*?)\*\*', r'<b style="color: white;">\1</b>', text)
        text = re.sub(r'\*(.*?)\*', r'<i>\1</i>', text)
        text = re.sub(r'`(.*?)`',
            r'<code style="background: #444; padding: 2px 4px; border-radius: 3px; font-family: monospace;">\1</code>',
            text)
        text = re.sub(
            r'\[([^\]]+)\]\((https?://[^\)]+)\)',
            lambda m: f'<a href="{m.group(2)}" style="color: {LINK_COLOR}; text-decoration: underline;">{m.group(1)}</a>',
            text)
        return text

    def is_table_row(s):
        return s.startswith('|') and s.endswith('|') and len(s) > 2

    def is_separator_row(s):
        return is_table_row(s) and all(c in '|-: ' for c in s)

    html = []
    lines = md_text.split('\n')
    in_list = False
    in_ordered = False
    in_table = False
    table_buf = []

    def flush_table():
        nonlocal table_buf, in_table
        if not table_buf:
            in_table = False
            return
        rows = [r for r in table_buf if not is_separator_row(r)]
        t = ['<table style="border-collapse: collapse; width: 100%; margin: 10px 0;">']
        for ri, row in enumerate(rows):
            cells = [c.strip() for c in row.strip('|').split('|')]
            if ri == 0:
                tag = 'th'
                sc = 'background:#313244; color:#cdd6f4; font-weight:bold; padding:6px 10px; border:1px solid #45475a;'
            else:
                tag = 'td'
                sc = 'padding:6px 10px; border:1px solid #45475a; color:#cdd6f4;'
            t.append('<tr>' + ''.join(f'<{tag} style="{sc}">{apply_inline(c)}</{tag}>' for c in cells) + '</tr>')
        t.append('</table>')
        html.extend(t)
        table_buf.clear()
        in_table = False

    def close_lists():
        nonlocal in_list, in_ordered
        if in_list:
            html.append('</ul>')
            in_list = False
        if in_ordered:
            html.append('</ol>')
            in_ordered = False

    for line in lines:
        line = line.rstrip()
        s = line.strip()

        if is_table_row(s):
            close_lists()
            in_table = True
            table_buf.append(s)
            continue
        elif in_table:
            flush_table()

        if s.startswith('---'):
            close_lists()
            html.append('<hr style="border: 0; border-top: 1px solid #555; margin: 10px 0;">')
            continue

        if s.startswith('#### '):
            close_lists()
            html.append(f'<h4 style="color: #b4c7fa; font-size: 14px; margin-top: 8px; margin-bottom: 4px;">{apply_inline(s[5:])}</h4>')
            continue
        elif s.startswith('### '):
            close_lists()
            html.append(f'<h3 style="color: #93c5fd; font-size: 16px; margin-top: 10px; margin-bottom: 5px;">{apply_inline(s[4:])}</h3>')
            continue
        elif s.startswith('## '):
            close_lists()
            html.append(f'<h2 style="color: #60a5fa; font-size: 18px; margin-top: 15px; margin-bottom: 8px;">{apply_inline(s[3:])}</h2>')
            continue
        elif s.startswith('# '):
            close_lists()
            html.append(f'<h1 style="color: #3b82f6; font-size: 22px; margin-bottom: 10px;">{apply_inline(s[2:])}</h1>')
            continue

        if s.startswith('- ') or s.startswith('* '):
            if in_ordered:
                html.append('</ol>')
                in_ordered = False
            if not in_list:
                html.append('<ul style="margin: 5px 0; padding-left: 20px;">')
                in_list = True
            html.append(f'<li style="margin-bottom: 4px;">{apply_inline(s[2:])}</li>')
            continue

        ol_m = re.match(r'^(\d+)\.\s+(.*)', s)
        if ol_m:
            if in_list:
                html.append('</ul>')
                in_list = False
            if not in_ordered:
                html.append('<ol style="margin: 5px 0; padding-left: 20px;">')
                in_ordered = True
            html.append(f'<li style="margin-bottom: 4px;">{apply_inline(ol_m.group(2))}</li>')
            continue

        close_lists()

        if not s:
            html.append('<br>')
            continue

        html.append(f'<p style="margin-bottom: 8px; line-height: 1.5;">{apply_inline(s)}</p>')

    if in_table:
        flush_table()
    close_lists()

    return "\n".join(html)


def get_unique_filepath(target_dir, filename):
    """
    Generates a unique filepath in target_dir based on filename.
    If filename exists, finds the next free index: file (1).txt, file (2).txt, etc.
    """
    base_name, ext = os.path.splitext(filename)
    candidate = filename
    full_path = os.path.join(target_dir, candidate)
    
    counter = 1
    while os.path.exists(full_path):
        candidate = f"{base_name} ({counter}){ext}"
        full_path = os.path.join(target_dir, candidate)
        counter += 1
        
    return full_path

def format_compact_count(value: int) -> str:
    """
    Компактно и локализованно форматирует большие числа для элементов UI.
    Например: 450 -> "450", 1100 -> "1.1к" (или "1.1k"), 30300 -> "30.3к", 31000 -> "31.0к".
    """
    if value is None or value <= 0:
        return "0"
    if value < 1000:
        return str(value)
        
    try:
        from config import AppContext
        suffix = "к" if AppContext.LANG.upper() == "RU" else "k"
    except:
        suffix = "к"
        
    val = value / 1000.0
    return f"{val:.1f}{suffix}"

def is_subpath(path: str, parent: str) -> bool:
    """
    Безопасно проверяет, является ли путь `path` подпутем родительского пути `parent`.
    Корректно обрабатывает регистр символов в Windows, различия в слэшах
    и предотвращает частичное совпадение имен папок (например, 'Folder2' и 'Folder22').
    """
    if not path or not parent:
        return False
    p = os.path.normcase(os.path.normpath(path))
    p_parent = os.path.normcase(os.path.normpath(parent))
    if p == p_parent:
        return True
    p_parent_sep = p_parent if p_parent.endswith(os.sep) else p_parent + os.sep
    return p.startswith(p_parent_sep)


def reveal_in_explorer(path: str) -> bool:
    """
    Открывает папку в проводнике Windows и выделяет файл (нативный Shell API).
    Для других ОС или в случае сбоя пытается использовать стандартное открытие.
    """
    import logging
    import sys
    path = os.path.abspath(path)
    if path.startswith('\\\\?\\'):
        path = path[4:]
    
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        
        shell32 = ctypes.windll.shell32
        ole32 = ctypes.windll.ole32
        
        LPITEMIDLIST = ctypes.c_void_p
        
        # Настройка типов ctypes
        shell32.ILCreateFromPathW.argtypes = [wintypes.LPCWSTR]
        shell32.ILCreateFromPathW.restype = LPITEMIDLIST
        
        shell32.ILFree.argtypes = [LPITEMIDLIST]
        shell32.ILFree.restype = None
        
        shell32.SHOpenFolderAndSelectItems.argtypes = [
            LPITEMIDLIST,
            wintypes.UINT,
            ctypes.POINTER(LPITEMIDLIST),
            wintypes.DWORD
        ]
        shell32.SHOpenFolderAndSelectItems.restype = ctypes.HRESULT
        
        dir_path = os.path.dirname(path)
        
        ole32.CoInitialize(None)
        try:
            dir_pidl = shell32.ILCreateFromPathW(dir_path)
            if not dir_pidl:
                raise Exception("Failed to create PIDL for directory")
                
            file_pidl = shell32.ILCreateFromPathW(path)
            if not file_pidl:
                shell32.ILFree(dir_pidl)
                raise Exception("Failed to create PIDL for file")
                
            apidl = (LPITEMIDLIST * 1)(file_pidl)
            hr = shell32.SHOpenFolderAndSelectItems(dir_pidl, 1, apidl, 0)
            
            shell32.ILFree(dir_pidl)
            shell32.ILFree(file_pidl)
            
            if hr < 0:
                raise Exception(f"SHOpenFolderAndSelectItems failed: {hex(hr & 0xffffffff)}")
            return True
        except Exception as e:
            logging.error(f"Native reveal failed: {e}. Falling back to startfile.")
            # Резервный вариант, если COM по какой-то причине сбоит
            try:
                os.startfile(dir_path)
                return True
            except Exception as start_err:
                logging.error(f"Fallback startfile failed: {start_err}")
                return False
        finally:
            ole32.CoUninitialize()
    else:
        # Для других ОС (Linux, macOS)
        try:
            import subprocess
            if sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', path])
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(path)])
            return True
        except Exception as e:
            logging.error(f"Non-Windows reveal failed: {e}")
            return False


