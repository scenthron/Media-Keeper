
import os

def smart_truncate_filename(full_text, max_width, font_metrics):
    """
    Умное сокращение: приоритет информации в скобках
    file.avi (150MB, H.264, 1920x1080) -> filen....avi (150MB, H.264, 1920x1080)
    """
    if font_metrics.horizontalAdvance(full_text) <= max_width:
        return full_text
    
    # Разделяем на имя и инфо в скобках
    if '(' in full_text and ')' in full_text:
        name_part = full_text[:full_text.index('(')].strip()
        info_part = full_text[full_text.index('('):]
    else:
        name_part = full_text
        info_part = ""
    
    # Проверяем длину инфо
    info_width = font_metrics.horizontalAdvance(info_part)
    available_for_name = max_width - info_width - font_metrics.horizontalAdvance("...")
    
    if available_for_name > 0:
        # Сокращаем имя, сохраняя расширение
        if '.' in name_part:
            base, ext = os.path.splitext(name_part)
            ext_width = font_metrics.horizontalAdvance(ext)
            available_for_base = available_for_name - ext_width
            
            if available_for_base > 0:
                # Подбираем длину базового имени
                for i in range(len(base), 0, -1):
                    test_text = base[:i] + "..." + ext + " " + info_part
                    if font_metrics.horizontalAdvance(test_text) <= max_width:
                        return test_text
    
    # Если и это не помещается, сокращаем и инфо
    if info_part:
        # Сокращаем инфо: (150MB...) 
        half_available = max_width // 2
        # Простое сокращение имени
        short_name = name_part[:5] + "..." + (name_part[-4:] if len(name_part) > 9 else "")
        remaining = max_width - font_metrics.horizontalAdvance(short_name + " (") - font_metrics.horizontalAdvance("...)")
        
        if remaining > 0:
            info_content = info_part[1:-1]  # Убираем скобки
            for i in range(len(info_content), 0, -1):
                test_info = "(" + info_content[:i] + "...)"
                if font_metrics.horizontalAdvance(test_info) <= remaining:
                    return short_name + " " + test_info
    
    # Крайний случай - просто обрезаем
    return full_text[:max_width // font_metrics.averageCharWidth()] + "..."

def format_file_info(name, size, codec, res):
    """
    Форматирует информацию о файле для отображения в ячейке
    Принимает 4 аргумента: имя, размер(байт), кодек, разрешение
    """
    size_mb = size / (1024 * 1024)
    return f"{name} ({size_mb:.0f}MB, {codec}, {res})"


def is_segment_taken(num_markers: int, segment_index: int, is_inverted: bool) -> bool:
    """Determines if a segment should be taken based on marker count and inversion."""
    if num_markers == 2:
        take = (segment_index == 1)
    else:
        take = (segment_index % 2 == 0)
    if is_inverted:
        take = not take
    return take