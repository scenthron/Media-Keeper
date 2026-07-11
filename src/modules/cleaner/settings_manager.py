import os
import json
import logging
from logic_paths import get_app_data_dir

class SimilarSettings:
    FILE_NAME = "similar_settings.json"

    def __init__(self):
        self.settings_file = os.path.join(get_app_data_dir(), self.FILE_NAME)
        self.settings = self._load_from_disk()

    def _load_from_disk(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to load similar settings: {e}")
        
        return {
            "image": self._get_default_image_settings(),
            "audio": self._get_default_audio_settings(),
            "video": self._get_default_video_settings()
        }

    def _save_to_disk(self):
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            logging.error(f"Failed to save similar settings: {e}")

    def _get_default_image_settings(self):
        return {
            "algorithm": 0, # pHash
            "resolution": 1, # 8x8
            "monotone_filter": False,
            "similarity": 95.0, # 95% default for images (range 5%)
            "range": 0, # 5%
            "video_frames": 2 # corresponds to index 2 (5 frames)
        }

    def _get_default_audio_settings(self):
        return {
            "algorithm": 0,
            "resolution": 1,
            "monotone_filter": False,
            "similarity": 90.0, # 90% default for audio
            "range": 1, # 10%
            "video_frames": 2
        }

    def _get_default_video_settings(self):
        return {
            "algorithm": 0, # pHash
            "resolution": 1, # 8x8 (index 1)
            "monotone_filter": False,
            "similarity": 95.0, # 95% default for video (requested by user)
            "range": 3, # 30% (index 3)
            "video_frames": 0 # 1 frame (index 0)
        }

    def load_settings(self, media_type_idx):
        if media_type_idx == 0:
            return self.settings.get("image", self._get_default_image_settings())
        elif media_type_idx == 1:
            return self.settings.get("audio", self._get_default_audio_settings())
        elif media_type_idx == 2:
            return self.settings.get("video", self._get_default_video_settings())
        return self._get_default_image_settings()

    def save_settings(self, media_type_idx, data):
        if media_type_idx == 0:
            self.settings["image"] = data
        elif media_type_idx == 1:
            self.settings["audio"] = data
        elif media_type_idx == 2:
            self.settings["video"] = data
        
        self._save_to_disk()

    def reset_settings(self, media_type_idx):
        if media_type_idx == 0:
            self.settings["image"] = self._get_default_image_settings()
            ret = self.settings["image"]
        elif media_type_idx == 1:
            self.settings["audio"] = self._get_default_audio_settings()
            ret = self.settings["audio"]
        elif media_type_idx == 2:
            self.settings["video"] = self._get_default_video_settings()
            ret = self.settings["video"]
        else:
            ret = self._get_default_image_settings()
            
        self._save_to_disk()
        return ret
