import subprocess
import os
import json
import tempfile
import logging
from typing import List, Tuple
from .dhash import get_image_ahash

CREATE_NO_WINDOW = 0x08000000

def get_video_duration(filepath: str, ffprobe_path: str) -> float:
    cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    try:
        if os.name == 'nt':
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=10)
        else:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if res.returncode == 0 and res.stdout.strip():
            return float(res.stdout.strip())
    except Exception as e:
        logging.error(f"Failed to get duration for {filepath}: {e}")
    return 0.0

def get_video_resolution(filepath: str, ffprobe_path: str) -> str:
    cmd = [ffprobe_path, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", filepath]
    try:
        if os.name == 'nt':
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=5)
        else:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip() # e.g. "1920x1080"
    except Exception:
        pass
    return "Unknown"

def get_video_bitrate(filepath: str, ffprobe_path: str) -> str:
    cmd = [ffprobe_path, "-v", "error", "-show_entries", "format=bit_rate", "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    try:
        if os.name == 'nt':
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=5)
        else:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        if res.returncode == 0 and res.stdout.strip() and res.stdout.strip() != "N/A":
            bitrate_bps = int(res.stdout.strip())
            return f"{bitrate_bps // 1000} kbps"
    except Exception:
        pass
    return ""

def extract_video_fingerprint(filepath: str, ffmpeg_path: str, ffprobe_path: str, hash_size: int = 16, algorithm: str = "ahash", frames_count: int = 5) -> Tuple[List[str], str]:
    """
    Extracts keyframes from the video and calculates hashes for each.
    Returns (list of hex hashes, resolution_string).
    """
    if not os.path.exists(ffmpeg_path) or not os.path.exists(ffprobe_path):
        raise FileNotFoundError("ffmpeg/ffprobe not found")

    duration = get_video_duration(filepath, ffprobe_path)
    res_str = get_video_resolution(filepath, ffprobe_path)
    bit_str = get_video_bitrate(filepath, ffprobe_path)
    if bit_str:
        res_str = f"{res_str} | {bit_str}"
    
    if duration <= 0:
        return [], res_str
        
    start_ts = duration * 0.1
    end_ts = duration * 0.9
    eff_duration = end_ts - start_ts
    if eff_duration <= 0:
        return [], res_str
        
    max_keep = frames_count
    hashes = []
    
    with tempfile.TemporaryDirectory() as tmpdir:
        step = eff_duration / (frames_count + 1)
        
        for i in range(1, frames_count + 1):
            if len(hashes) >= max_keep:
                break
                
            ts = start_ts + step * i
            out_img = os.path.join(tmpdir, f"frame_{i}.jpg")
            cmd = [ffmpeg_path, "-y", "-ss", f"{ts:.3f}", "-i", filepath, "-vframes", "1", "-q:v", "5", out_img]
            try:
                if os.name == 'nt':
                    subprocess.run(cmd, capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=10)
                else:
                    subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    
                if os.path.exists(out_img):
                    if algorithm == "phash":
                        from .dhash import get_image_phash as get_hash
                    elif algorithm == "dhash":
                        from .dhash import get_image_dhash as get_hash
                    else:
                        from .dhash import get_image_ahash as get_hash
                        
                    h_val, _, std_dev = get_hash(out_img, hash_size)
                    # Фильтр однородных (черных/белых) кадров: std_dev > 10.0
                    if h_val and std_dev > 10.0:
                        hashes.append(h_val)
            except Exception as e:
                logging.error(f"Failed to extract frame {i} for {filepath}: {e}")
                
    return hashes, res_str

def hamming_hex(hex1: str, hex2: str) -> int:
    """Calculates Hamming distance between two hex strings."""
    if len(hex1) != len(hex2):
        return 999999
    # Convert hex to int, XOR, count 1s
    val1 = int(hex1, 16)
    val2 = int(hex2, 16)
    return bin(val1 ^ val2).count('1')

def compare_video_fingerprints(hashes1: List[str], hashes2: List[str], hash_size: int = 16) -> float:
    """
    Compares two lists of video hashes using a sliding window of +/- 1 frame to account for minor shifts.
    Returns similarity percentage (0.0 to 100.0).
    """
    if not hashes1 or not hashes2:
        return 0.0
        
    bits_per_hash = hash_size * hash_size
    
    # Убеждаемся, что hashes1 - более короткий (или равный) список
    if len(hashes1) > len(hashes2):
        hashes1, hashes2 = hashes2, hashes1
        
    num_frames1 = len(hashes1)
    num_frames2 = len(hashes2)
    
    best_overall_sim = 0.0
    
    # Скользим коротким массивом по длинному
    for offset in range(-1, num_frames2 - num_frames1 + 2):
        total_dist = 0
        compared_frames = 0
        for i in range(num_frames1):
            j = i + offset
            if 0 <= j < num_frames2:
                dist = hamming_hex(hashes1[i], hashes2[j])
                total_dist += dist
                compared_frames += 1
                
        if compared_frames > 0:
            max_dist = compared_frames * bits_per_hash
            sim = (max_dist - total_dist) / max_dist * 100.0
            if sim > best_overall_sim:
                best_overall_sim = sim
                
    return best_overall_sim
