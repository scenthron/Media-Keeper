import subprocess
import os
import json
import logging
from typing import List

# Windows specific flag to prevent popping up console windows
CREATE_NO_WINDOW = 0x08000000

def popcount(n: int) -> int:
    """Returns the number of set bits (1s) in a 32-bit integer."""
    return bin(n).count('1')

def extract_audio_fingerprint(filepath: str, fpcalc_path: str) -> List[int]:
    """
    Calls fpcalc.exe to extract raw audio fingerprint (first 120 seconds).
    Returns a list of 32-bit integers.
    """
    if not os.path.exists(fpcalc_path):
        raise FileNotFoundError(f"fpcalc executable not found at {fpcalc_path}")

    # Use -raw to get integer array, -json to parse easily, -length 120 for 2 mins
    cmd = [fpcalc_path, "-raw", "-json", "-length", "120", filepath]
    
    try:
        if os.name == 'nt':
            result = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=15)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
        if result.returncode != 0:
            logging.error(f"fpcalc failed for {filepath}: {result.stderr}")
            return []
            
        data = json.loads(result.stdout)
        fingerprint = data.get("fingerprint", [])
        return fingerprint
    except Exception as e:
        logging.error(f"Failed to extract audio fingerprint for {filepath}: {e}")
        return []

def compare_audio_fingerprints(fp1: List[int], fp2: List[int], max_offset: int = 30) -> float:
    """
    Compares two raw chromaprint fingerprints using a sliding window.
    Returns similarity percentage (0.0 to 100.0).
    max_offset = 30 frames means sliding +/- 3.5 seconds to align.
    """
    if not fp1 or not fp2:
        return 0.0
        
    len1 = len(fp1)
    len2 = len(fp2)
    
    if min(len1, len2) == 0:
        return 0.0

    # Ensure fp1 is the shorter one to slide it over fp2
    if len1 > len2:
        fp1, fp2 = fp2, fp1
        len1, len2 = len2, len1
        
    best_similarity = 0.0
    
    # We will slide fp1 over fp2.
    if max_offset > 100:
        max_offset = 100

    start_offset = max(-max_offset, -len1 + 1)
    end_offset = min(len2 - len1 + max_offset, len2 - 1)
    
    # Оптимизация 1: Сначала проверяем смещение 0 (точная копия)
    # Если находим совпадение > 95%, сразу возвращаем его (Early Exit)
    offsets_to_check = [0] + [off for off in range(start_offset, end_offset + 1) if off != 0]
    
    has_bit_count = hasattr(int, 'bit_count')
    
    for offset in offsets_to_check:
        # Calculate overlap bounds
        start1 = max(0, -offset)
        end1 = min(len1, len2 - offset)
        
        overlap_len = end1 - start1
        if overlap_len < min(len1, len2) * 0.5 or overlap_len < 20:
            continue
                
        diff_bits = 0
        
        # Оптимизация 2: Использование аппаратного bit_count вместо создания строк bin().count()
        if has_bit_count:
            for i in range(start1, end1):
                diff_bits += (fp1[i] ^ fp2[i + offset]).bit_count()
        else:
            for i in range(start1, end1):
                diff_bits += bin(fp1[i] ^ fp2[i + offset]).count('1')
            
        total_bits = overlap_len * 32
        if total_bits > 0:
            sim = (total_bits - diff_bits) / float(total_bits) * 100.0
            if sim > best_similarity:
                best_similarity = sim
            
            # Early Exit для почти точных копий (предотвращает лишние сдвиги)
            if best_similarity >= 98.0:
                return best_similarity
                
    return best_similarity
