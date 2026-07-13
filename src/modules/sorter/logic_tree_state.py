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
                data = json.load(f)
                
            root_norm = os.path.normpath(root_path)
            
            if "collapsed_states" in data:
                new_states = {}
                for rel_k, v in data["collapsed_states"].items():
                    if rel_k == "." or rel_k == "":
                        abs_k = root_norm
                    else:
                        abs_k = os.path.normpath(os.path.join(root_norm, rel_k))
                    new_states[abs_k] = v
                data["collapsed_states"] = new_states
                
            if "custom_orders" in data:
                new_orders = {}
                for rel_k, v in data["custom_orders"].items():
                    if rel_k == "." or rel_k == "":
                        abs_k = root_norm
                    else:
                        abs_k = os.path.normpath(os.path.join(root_norm, rel_k))
                    new_orders[abs_k] = v
                data["custom_orders"] = new_orders
                
            return data
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
        root_norm = os.path.normpath(root_path)
        
        rel_states = {}
        for k, v in collapsed_states.items():
            try:
                rel_k = os.path.relpath(k, root_norm)
                # Ensure slashes are uniform, though JSON dumps whatever string we give it.
                # using forward slashes makes the JSON cleaner and cross-platform
                rel_k = rel_k.replace('\\', '/')
            except ValueError:
                rel_k = k
            rel_states[rel_k] = v
            
        rel_orders = {}
        for k, v in custom_orders.items():
            try:
                rel_k = os.path.relpath(k, root_norm)
                rel_k = rel_k.replace('\\', '/')
            except ValueError:
                rel_k = k
            rel_orders[rel_k] = v
        
        data = {
            "enabled": is_enabled,
            "collapsed_states": rel_states,
            "custom_orders": rel_orders
        }
        
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            logging.error(f"Failed to save tree state to {path}: {e}")
