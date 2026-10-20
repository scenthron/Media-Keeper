
import os

def smart_truncate_filename(full_text, max_width, font_metrics):
    """
    Умное сокращение середины имени файла:
    file_very_long_name.avi (150MB, H.264, 1920x1080) -> file_v...name.avi (150MB, H.264, 1920x1080)
    Всегда сохраняет расширение файла и информацию в скобках.
    """
    if not full_text or font_metrics.horizontalAdvance(full_text) <= max_width:
        return full_text
        
    if '(' in full_text and full_text.endswith(')'):
        idx = full_text.rfind('(')
        name_part = full_text[:idx].strip()
        info_part = full_text[idx:].strip()
    else:
        name_part = full_text
        info_part = ""
        
    base, ext = os.path.splitext(name_part)
    info_str = f" {info_part}" if info_part else ""
    info_w = font_metrics.horizontalAdvance(info_str)
    
    avail_for_name = max_width - info_w
    min_name_w = font_metrics.horizontalAdvance("..." + ext)
    
    if avail_for_name <= min_name_w:
        from PyQt6.QtCore import Qt
        return font_metrics.elidedText(full_text, Qt.TextElideMode.ElideMiddle, max_width)
        
    low = 1
    high = len(base)
    best_name = base + ext
    
    while low <= high:
        mid = (low + high) // 2
        left_len = (mid + 1) // 2
        right_len = mid // 2
        candidate = base[:left_len] + "..." + (base[-right_len:] if right_len > 0 else "") + ext
        if font_metrics.horizontalAdvance(candidate) <= avail_for_name:
            best_name = candidate
            low = mid + 1
        else:
            high = mid - 1
            
    return f"{best_name}{info_str}"

def format_file_info(name, size, codec=None, res=None):
    """
    Форматирует информацию о файле для отображения в ячейке.
    Принимает 4 аргумента: имя, размер (байт), кодек/длительность, разрешение.
    """
    if size < 1024 * 1024:
        size_str = f"{size / 1024:.0f}KB"
    elif size < 10 * 1024 * 1024:
        size_str = f"{size / (1024 * 1024):.1f}MB"
    else:
        size_str = f"{size / (1024 * 1024):.0f}MB"
        
    parts = [size_str]
    if codec:
        parts.append(str(codec).strip())
    if res and str(res).strip() not in ("?", ""):
        parts.append(str(res).strip())
        
    info_str = ", ".join(parts)
    return f"{name} ({info_str})"


def is_segment_taken(num_markers: int, segment_index: int, is_inverted: bool) -> bool:
    """Determines if a segment should be taken based on marker count and inversion."""
    if num_markers == 2:
        take = (segment_index == 1)
    else:
        take = (segment_index % 2 == 0)
    if is_inverted:
        take = not take
    return take


def format_ms_time(ms: int) -> str:
    """Formats milliseconds into MM:SS.mmm or HH:MM:SS.mmm string."""
    if ms < 0:
        ms = 0
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    sss = ms % 1000
    if h > 0:
        return f"{h:02}:{m:02}:{s:02}.{sss:03}"
    return f"{m:02}:{s:02}.{sss:03}"
