import os
import json
import logging

class TreeStateManager:
    META_DIR = ".mediakeeper"
    CONF_FILE = "treeview.json"

    @staticmethod
    def get_state_path(root_path):
        return os.path.join(root_path, TreeStateManager.META_DIR, TreeStateManager.CONF_FILE)

    @staticmethod
    def state_exists(root_path):
        return os.path.exists(TreeStateManager.get_state_path(root_path))

    @staticmethod
    def load_state(root_path):
        path = TreeStateManager.get_state_path(root_path)
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"Failed to load tree state from {path}: {e}")
            return None

    @staticmethod
    def save_state(root_path, is_enabled, collapsed_states, custom_orders):
        if not root_path or not os.path.exists(root_path):
            return
            
        meta_dir = os.path.join(root_path, TreeStateManager.META_DIR)
        os.makedirs(meta_dir, exist_ok=True)
        # Windows hides dot folders
        try:
            import ctypes
            FILE_ATTRIBUTE_HIDDEN = 0x02
            ctypes.windll.kernel32.SetFileAttributesW(meta_dir, FILE_ATTRIBUTE_HIDDEN)
        except:
            pass

        path = TreeStateManager.get_state_path(root_path)
        
        data = {
            "enabled": is_enabled,
            "collapsed_states": collapsed_states,
            "custom_orders": custom_orders
        }
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Failed to save tree state to {path}: {e}")
