
import os
import logging
from PyQt6.QtCore import QThread, pyqtSignal

class AnalyzerWorker(QThread):
    """
    Scans directory recursively (FULL DEPTH) to calculate correct sizes.
    Returns:
    1. Tree structure (for Sunburst)
    2. Stats Map (for Summary Table) -> { '.ext': {'size': 0, 'count': 0, 'files': [{name, path, size}]} }
    """
    finished_analysis = pyqtSignal(dict, dict) 
    progress_update = pyqtSignal(int)

    def __init__(self, path):
        super().__init__()
        self.path = path
        self.scanned_count = 0
        self.is_running = True
        
        self.stats_map = {} # Aggregate stats by extension

    def build_tree(self, current_path):
        if not self.is_running: return None

        node = {
            'name': os.path.basename(current_path) or current_path,
            'path': current_path,
            'type': 'dir',
            'size': 0,
            'children': []
        }

        try:
            with os.scandir(current_path) as it:
                entries = list(it)
                
                for entry in entries:
                    if not self.is_running: break
                    
                    self.scanned_count += 1
                    if self.scanned_count % 500 == 0:
                        self.progress_update.emit(self.scanned_count)

                    if entry.is_dir(follow_symlinks=False):
                        # Recursive call (No depth limit in Worker to ensure full size calc)
                        child_node = self.build_tree(entry.path)
                        if child_node:
                            node['size'] += child_node['size']
                            node['children'].append(child_node)
                    
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            size = entry.stat().st_size
                            node['size'] += size
                            
                            ext = os.path.splitext(entry.name)[1].lower()
                            
                            # Add to Tree
                            node['children'].append({
                                'name': entry.name,
                                'path': entry.path,
                                'type': 'file',
                                'size': size,
                                'children': []
                            })
                            
                            # Add to Stats Map
                            if ext not in self.stats_map:
                                self.stats_map[ext] = {'size': 0, 'count': 0, 'files': []}
                            
                            self.stats_map[ext]['size'] += size
                            self.stats_map[ext]['count'] += 1
                            self.stats_map[ext]['files'].append({
                                'name': entry.name, 
                                'path': entry.path, 
                                'size': size
                            })
                            
                        except Exception: pass
                        
        except PermissionError:
            pass
        except Exception as e:
            logging.error(f"Error scanning {current_path}: {e}")

        # Sorting logic is handled in the UI/Chart level to keep worker pure
        return node

    def run(self):
        logging.info(f"Analyzer started for {self.path} (Full Depth)")
        if not os.path.exists(self.path):
            self.finished_analysis.emit({}, {})
            return

        self.scanned_count = 0
        self.stats_map = {}
        
        root_node = self.build_tree(self.path)
        
        if self.is_running and root_node:
            self.finished_analysis.emit(root_node, self.stats_map)
        else:
            self.finished_analysis.emit({}, {})

    def stop(self):
        self.is_running = False
