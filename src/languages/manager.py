
import os
import json
import logging
from logic_paths import find_resource_dir

class LanguageManager:
    """
    Manages loading of modular JSON translation files.
    Implements Fallback Strategy: Always loads EN first, then overlays target language.
    """
    _current_dict = {}
    _manual_content = "# Manual not found"
    _manual_contents = {}
    
    BASE_LANG = "EN"
    
    @staticmethod
    def get_lang_dir():
        """Returns path to src/languages using independent logic"""
        return find_resource_dir("languages")

    @staticmethod
    def get_available_languages():
        """Scans directory for folders containing meta.json"""
        langs = []
        root = LanguageManager.get_lang_dir()
        if not root or not os.path.exists(root):
            return ["EN"]
            
        for item in os.listdir(root):
            path = os.path.join(root, item)
            if os.path.isdir(path) and os.path.exists(os.path.join(path, "meta.json")):
                try:
                    with open(os.path.join(path, "meta.json"), 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                        code = meta.get("code", item.upper())
                        langs.append(code)
                except:
                    pass
        
        if "EN" not in langs: langs.insert(0, "EN")
        return sorted(list(set(langs)))

    @staticmethod
    def load_language(lang_code):
        """
        Loads translations.
        1. Load BASE_LANG (EN) to ensure all keys exist.
        2. If lang_code != EN, load target language and update (overwrite) keys.
        """
        # We use print here because logging might not be initialized when config is first imported
        print(f"[LANG] Loading language: {lang_code}")
        root = LanguageManager.get_lang_dir()
        if not root:
            print("[LANG][CRITICAL] Languages directory not found via logic_paths!")
            return

        final_dict = {}

        # 1. Load Base (Fallback)
        base_path = os.path.join(root, LanguageManager.BASE_LANG.lower())
        if os.path.exists(base_path):
            final_dict.update(LanguageManager._load_folder_json(base_path))
        else:
            print(f"[LANG][ERROR] Base language folder not found at: {base_path}")
        
        # 2. Load Target (Overlay)
        if lang_code != LanguageManager.BASE_LANG:
            target_path = os.path.join(root, lang_code.lower())
            if os.path.exists(target_path):
                target_dict = LanguageManager._load_folder_json(target_path)
                final_dict.update(target_dict)
            else:
                print(f"[LANG][WARN] Target language folder not found at: {target_path}")

        if not final_dict:
            print("[LANG][CRITICAL] Final dictionary is empty! Check json files.")

        LanguageManager._current_dict = final_dict
        
        # 3. Load Manual
        LanguageManager._load_manual(lang_code)

    @staticmethod
    def _load_folder_json(folder_path):
        """Helper: Reads all .json files in a folder and merges them into one dict."""
        merged = {}
        try:
            for filename in os.listdir(folder_path):
                if filename.endswith(".json") and filename != "meta.json":
                    file_path = os.path.join(folder_path, filename)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if isinstance(data, dict):
                                merged.update(data)
                            else:
                                print(f"[LANG][ERR] {filename} is not a valid JSON dictionary")
                    except Exception as e:
                        print(f"[LANG][ERR] Error parsing {filename}: {e}")
        except Exception as e:
            print(f"[LANG][ERR] Error accessing language folder {folder_path}: {e}")
        return merged

    @staticmethod
    def _load_manual(lang_code):
        root = LanguageManager.get_lang_dir()
        if not root: return

        # Load general manual (About)
        man_path = os.path.join(root, lang_code.lower(), "manual.md")
        if not os.path.exists(man_path) and lang_code != LanguageManager.BASE_LANG:
            man_path = os.path.join(root, LanguageManager.BASE_LANG.lower(), "manual.md")
        if os.path.exists(man_path):
            try:
                with open(man_path, 'r', encoding='utf-8') as f:
                    LanguageManager._manual_content = f.read()
            except Exception as e:
                print(f"[LANG] Failed to load manual {man_path}: {e}")
                LanguageManager._manual_content = "# Error loading manual"
        else:
            LanguageManager._manual_content = "# Manual not found"

        # Load sections
        sections = ["about", "sorter", "analyzer", "cleaner", "editor"]
        for sec in sections:
            filename = f"manual_{sec}.md" if sec != "about" else "manual.md"
            sec_path = os.path.join(root, lang_code.lower(), filename)
            if not os.path.exists(sec_path) and lang_code != LanguageManager.BASE_LANG:
                sec_path = os.path.join(root, LanguageManager.BASE_LANG.lower(), filename)
            
            if os.path.exists(sec_path):
                try:
                    with open(sec_path, 'r', encoding='utf-8') as f:
                        LanguageManager._manual_contents[sec] = f.read()
                except Exception as e:
                    print(f"[LANG] Failed to load manual {sec_path}: {e}")
                    LanguageManager._manual_contents[sec] = f"# Error loading {sec} manual"
            else:
                LanguageManager._manual_contents[sec] = f"# Manual for {sec} not found"

    @staticmethod
    def tr(key):
        return LanguageManager._current_dict.get(key, key)

    @staticmethod
    def get_manual_md():
        return LanguageManager._manual_content

    @staticmethod
    def get_manual_section_md(sec):
        return LanguageManager._manual_contents.get(sec, "# Section not found")
