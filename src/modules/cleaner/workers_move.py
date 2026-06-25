
import os
import shutil
import logging
import threading
from PyQt6.QtCore import QThread, pyqtSignal
from utils_io import smart_move_file
import secrets
import random
import string

def ensure_long_path(path):
    r"""
    Ensure the path handles Windows long paths (prefix \\?\).
    """
    if os.name == 'nt' and not path.startswith('\\\\?\\'):
        return '\\\\?\\' + os.path.abspath(path)
    return path

class SessionMoveWorker(QThread):
    progress_total = pyqtSignal(int, int)
    file_started = pyqtSignal(str)
    file_progress = pyqtSignal(int, int)
    finished = pyqtSignal(list, int, set)

    def __init__(self, items, dest_root, rename_idx, preserve_struct):
        super().__init__()
        self.items = items
        self.dest_root = dest_root
        # rename_idx mapping:
        # 0: Standard Increment (Name -> Name (1))
        # 1: Mark Duple (Name -> Name_duple)
        # 2: Random Hex (Name -> Name_a1b2)
        self.rename_idx = rename_idx 
        self.preserve_struct = preserve_struct
        self.stop_event = threading.Event()

    def stop(self):
        self.stop_event.set()

    def run(self):
        moved_paths = []
        errors = 0
        total = len(self.items)
        affected_groups = set()
        
        long_dest_root = ensure_long_path(self.dest_root)
        
        for idx, entry in enumerate(self.items):
            if self.stop_event.is_set(): break
            
            src_path = ensure_long_path(entry['src'])
            group_index = entry.get('group_index', -1)
            
            self.file_started.emit(os.path.basename(src_path))
            
            try:
                if not os.path.exists(src_path):
                    errors += 1
                    self.progress_total.emit(idx + 1, total)
                    continue
                
                filename = os.path.basename(src_path)
                name_base, name_ext = os.path.splitext(filename)
                
                # 1. Calculate Target Directory
                if self.preserve_struct:
                    # Recreate structure: Dest / DriveLetter / OriginalPath...
                    drive, tail = os.path.splitdrive(src_path)
                    
                    # Strip long path prefix from drive to avoid os.path.join breaking
                    if drive.startswith('\\\\?\\'):
                        drive = drive[4:]
                        
                    drive_clean = drive.replace(':', '')
                    rel_path = os.path.dirname(tail)
                    if rel_path.startswith(os.sep): rel_path = rel_path[1:]
                    
                    target_dir = os.path.join(long_dest_root, drive_clean, rel_path)
                else:
                    target_dir = long_dest_root
                
                os.makedirs(target_dir, exist_ok=True)
                
                # 2. Apply Renaming Strategy (Base Name Calculation)
                candidate_name = filename
                
                if self.rename_idx == 1: # Mark Duple
                    candidate_name = f"{name_base}_duple{name_ext}"
                elif self.rename_idx == 2: # Random Hex
                    suffix = secrets.token_hex(3)
                    candidate_name = f"{name_base}_{suffix}{name_ext}"
                # else (idx 0): Standard, keep original name initially
                
                # 3. Handle Collisions (Smart Increment)
                # If file exists, we append (1), (2), etc. 
                # This applies to ALL strategies to guarantee uniqueness.
                
                target_path = os.path.join(target_dir, candidate_name)
                
                if os.path.exists(target_path):
                    counter = 1
                    base_for_increment = os.path.splitext(candidate_name)[0]
                    
                    while os.path.exists(target_path):
                        if self.stop_event.is_set(): break
                        new_name = f"{base_for_increment} ({counter}){name_ext}"
                        target_path = os.path.join(target_dir, new_name)
                        counter += 1
                
                # 4. Execute Move
                def progress_cb(moved, total_sz):
                    self.file_progress.emit(moved, total_sz)
                
                success = smart_move_file(src_path, target_path, progress_cb, self.stop_event)
                
                if success:
                    moved_paths.append(entry['src'])
                    if group_index != -1: affected_groups.add(group_index)
                else:
                    if not self.stop_event.is_set(): 
                        errors += 1
                        logging.error(f"Move failed (smart_move_file returned False) for: {src_path}")
                    
            except Exception as e:
                logging.error(f"Move Error: {e}")
                errors += 1
            
            self.progress_total.emit(idx + 1, total)
            
        self.finished.emit(moved_paths, errors, affected_groups)


class SessionDeleteWorker(QThread):
    progress_total = pyqtSignal(int, int)
    file_started = pyqtSignal(str)
    finished = pyqtSignal(list, list)

    def __init__(self, items: list[str], is_folders: bool = False, use_trash: bool = True) -> None:
        super().__init__()
        self.items: list[str] = items
        self.is_folders: bool = is_folders
        self.use_trash: bool = use_trash
        self.stop_event: threading.Event = threading.Event()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        deleted_paths: list[str] = []
        errors: list[tuple[str, str]] = []
        total: int = len(self.items)

        from PyQt6.QtCore import QFile
        import shutil

        for idx, path in enumerate(self.items):
            if self.stop_event.is_set():
                break

            self.file_started.emit(os.path.basename(path) if not self.is_folders else path)

            path_long = ensure_long_path(path)

            if not os.path.exists(path_long):
                deleted_paths.append(path)
                self.progress_total.emit(idx + 1, total)
                continue

            try:
                if self.is_folders:
                    shutil.rmtree(path_long, ignore_errors=True)
                    if not os.path.exists(path_long):
                        deleted_paths.append(path)
                    else:
                        try:
                            os.rmdir(path_long)
                            deleted_paths.append(path)
                        except OSError as e:
                            logging.error(f"Failed to delete empty folder {path}: {e}")
                            errors.append((path, str(e)))
                else:
                    if self.use_trash:
                        success = QFile.moveToTrash(path_long)
                        trash_ok = success[0] if isinstance(success, tuple) else bool(success)
                        if not trash_ok:
                            if os.path.isdir(path_long):
                                shutil.rmtree(path_long)
                            else:
                                os.remove(path_long)
                        deleted_paths.append(path)
                        logging.info(f"[Cleaner] Файл удален: {path}")
                    else:
                        if os.path.isdir(path_long):
                            shutil.rmtree(path_long)
                        else:
                            os.remove(path_long)
                        deleted_paths.append(path)
                        logging.info(f"[Cleaner] Файл удален жестко: {path}")
            except Exception as e:
                logging.error(f"[Cleaner] Не удалось удалить '{path}': {e}")
                errors.append((path, str(e)))

            self.progress_total.emit(idx + 1, total)

        self.finished.emit(deleted_paths, errors)

