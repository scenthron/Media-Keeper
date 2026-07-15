import os

# =============================================================================
# GLOBAL MEDIA EXTENSION LISTS
# =============================================================================
# All extensions should be lowercase and start with a dot.
# Use these sets throughout the codebase to ensure consistency.

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".tiff", ".tif", ".psd", ".raw", ".heic", ".heif", ".avif", ".apng", ".jfif"}
VIDEO_EXTS = {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".mpeg", ".mpg", ".3gp", ".ts", ".m2ts", ".vob", ".m2v", ".asf", ".rm", ".rmvb", ".divx", ".ogv", ".f4v", ".vro"}
AUDIO_EXTS = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a", ".opus", ".aiff", ".ape", ".mka", ".alac"}
DOC_EXTS   = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".rtf", ".odt", ".ods", ".odp", ".epub", ".mobi"}
ARCH_EXTS  = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".iso"}
CODE_EXTS  = {".py", ".js", ".html", ".css", ".json", ".xml", ".java", ".cpp", ".c", ".h", ".cs", ".php", ".rb", ".go", ".vue", ".jsx"}

# Extension categories matching cleaner module
EXT_CATEGORIES = {
    "Images": list(IMAGE_EXTS),
    "Video": list(VIDEO_EXTS),
    "Audio": list(AUDIO_EXTS),
    "Documents": list(DOC_EXTS),
    "Archives": list(ARCH_EXTS),
    "Code": list(CODE_EXTS),
}

# =============================================================================
# TOOL-SPECIFIC EXCLUSIONS
# =============================================================================
# If a specific tool (e.g. QMediaPlayer) cannot handle certain extensions, 
# exclude them here and use the get_filtered_exts() function.

TOOL_EXCLUSIONS = {
    # Внутренний плеер (QMediaPlayer) может не поддерживать некоторые форматы без кодеков.
    # Но если у пользователя установлен K-Lite Codec Pack, они будут работать!
    # Поэтому мы не блокируем их принудительно.
    "logic_player_video": set(),
    "logic_player_audio": set(),
}

def get_filtered_exts(base_set: set, tool_name: str) -> set:
    """
    Returns a set of extensions, excluding any formats defined in TOOL_EXCLUSIONS for the given tool_name.
    """
    exclusions = TOOL_EXCLUSIONS.get(tool_name, set())
    return base_set - exclusions
