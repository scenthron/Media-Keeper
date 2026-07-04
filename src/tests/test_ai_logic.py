import os
import tempfile
import sqlite3
import json
import numpy as np
import pytest
from unittest.mock import MagicMock, patch

from modules.cleaner.logic_ai_cache import AiCacheManager
from modules.cleaner.logic_ai_classifier import (
    AiClassifier, load_ai_settings, save_ai_settings, get_ai_assets_dir
)

@pytest.fixture
def temp_app_dir():
    """Создает временную директорию для тестирования настроек и баз данных."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('modules.cleaner.logic_ai_cache.get_app_data_dir', return_value=tmpdir), \
             patch('modules.cleaner.logic_ai_classifier.get_app_data_dir', return_value=tmpdir):
            yield tmpdir

def test_ai_cache_manager(temp_app_dir):
    """Тестирует сохранение и извлечение данных из SQLite-кэша ИИ."""
    cache = AiCacheManager()
    
    # 1. Тест кэша общих эмбеддингов
    filepath = os.path.join(temp_app_dir, "test_image.png")
    mtime = 1234567.89
    size = 1024
    embedding = np.random.rand(960).astype(np.float32)
    
    # Пытаемся получить несуществующий файл
    assert cache.get_image_embedding(filepath, mtime, size) is None
    
    # Сохраняем и считываем обратно
    cache.save_image_embedding(filepath, mtime, size, embedding)
    cached_emb = cache.get_image_embedding(filepath, mtime, size)
    
    assert cached_emb is not None
    assert np.allclose(cached_emb, embedding)
    
    # Проверяем, что при изменении mtime или размера кэш возвращает None
    assert cache.get_image_embedding(filepath, mtime + 1.0, size) is None
    assert cache.get_image_embedding(filepath, mtime, size + 5) is None
    
    # 2. Тест кэша лиц
    face_filepath = os.path.join(temp_app_dir, "test_face.png")
    face_mtime = 9876543.21
    face_size = 2048
    
    faces = [
        {"bbox": [10, 20, 50, 60], "descriptor": np.random.rand(128).astype(np.float32)},
        {"bbox": [100, 110, 40, 40], "descriptor": np.random.rand(128).astype(np.float32)}
    ]
    
    assert cache.get_file_faces(face_filepath, face_mtime, face_size) is None
    
    # Сохраняем и считываем
    cache.save_file_faces(face_filepath, face_mtime, face_size, faces)
    cached_faces = cache.get_file_faces(face_filepath, face_mtime, face_size)
    
    assert cached_faces is not None
    assert len(cached_faces) == 2
    assert cached_faces[0]["bbox"] == [10, 20, 50, 60]
    assert np.allclose(cached_faces[0]["descriptor"], faces[0]["descriptor"])
    
    # Проверяем неактуальный mtime
    assert cache.get_file_faces(face_filepath, face_mtime + 5, face_size) is None

def test_ai_settings():
    """Тестирует сохранение и чтение ai_settings.json."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch('modules.cleaner.logic_ai_classifier.get_ai_assets_dir', return_value=tmpdir):
            settings = load_ai_settings()
            assert settings == {"groups": {}}
            
            settings["groups"]["Test Group"] = {"type": "face", "enabled": True}
            save_ai_settings(settings)
            
            loaded = load_ai_settings()
            assert loaded["groups"]["Test Group"]["type"] == "face"
            assert loaded["groups"]["Test Group"]["enabled"] is True

def test_classifier_status_and_training(temp_app_dir):
    """Тестирует проверку статусов и обучение групп эталонов."""
    # Создаем тестовую группу на диске
    group_name = "Discord Screenshots"
    group_dir = os.path.join(temp_app_dir, "Ai_assets", group_name)
    os.makedirs(group_dir, exist_ok=True)
    
    # Настройки
    settings = {"groups": {group_name: {"type": "general", "enabled": True}}}
    with open(os.path.join(temp_app_dir, "Ai_assets", "ai_settings.json"), "w") as f:
        json.dump(settings, f)
        
    cache = AiCacheManager()
    ai_engine = MagicMock()
    
    classifier = AiClassifier(cache, ai_engine)
    
    # 1. Серый статус: в группе нет файлов
    status, count = classifier.get_group_status(group_name)
    assert status == "gray"
    assert count == 0
    
    # 2. Добавляем картинку
    test_img = os.path.join(group_dir, "ref1.png")
    with open(test_img, "wb") as f:
        f.write(b"fake image data")
        
    # Статус оранжевый: файлы есть, но в кэше пусто
    status, count = classifier.get_group_status(group_name)
    assert status == "orange"
    assert count == 1
    
    # 3. Обучаем группу (мокаем вызов экстрактора ИИ)
    fake_emb = np.random.rand(960).astype(np.float32)
    ai_engine.initialize_sessions.return_value = True
    ai_engine.extract_image_embedding.return_value = fake_emb
    
    trained = classifier.train_group(group_name)
    assert trained is True
    
    # Статус должен стать зеленым
    status, count = classifier.get_group_status(group_name)
    assert status == "green"
    assert count == 1
    
    # Проверяем, что вектор сохранился в кэше
    stat = os.stat(test_img)
    saved_emb = cache.get_image_embedding(test_img, stat.st_mtime, stat.st_size)
    assert saved_emb is not None
    assert np.allclose(saved_emb, fake_emb)

def test_classifier_matching(temp_app_dir):
    """Тестирует сопоставление (matching) файлов с активными эталонами."""
    cache = AiCacheManager()
    ai_engine = MagicMock()
    classifier = AiClassifier(cache, ai_engine)
    
    # Мокаем активные центроиды групп
    group_name = "Memes"
    centroid = np.zeros(960, dtype=np.float32)
    centroid[0] = 1.0 # Простой единичный вектор
    classifier.general_centroids[group_name] = centroid
    
    # Сканируемый файл
    scan_filepath = os.path.join(temp_app_dir, "scanned.jpg")
    with open(scan_filepath, "wb") as f:
        f.write(b"data")
        
    # Мокаем кэш и извлечение вектора
    # 1. Полное совпадение
    exact_emb = np.zeros(960, dtype=np.float32)
    exact_emb[0] = 1.0
    
    cache.save_image_embedding(scan_filepath, os.path.getmtime(scan_filepath), os.path.getsize(scan_filepath), exact_emb)
    
    best_group, confidence, details = classifier.match_image(scan_filepath, os.path.getmtime(scan_filepath), os.path.getsize(scan_filepath))
    assert best_group == group_name
    # similarity = dot(exact_emb, centroid) = 1.0
    # confidence = (1.0 - 0.3) / 0.7 * 100 = 100%
    assert abs(confidence - 100.0) < 0.01
    assert details["type"] == "general"
    
    # 2. Частичное совпадение (similarity = 0.65)
    part_emb = np.zeros(960, dtype=np.float32)
    part_emb[0] = 0.65
    part_emb[1] = np.sqrt(1.0 - 0.65**2) # Длина 1.0
    
    cache.save_image_embedding(scan_filepath, os.path.getmtime(scan_filepath), os.path.getsize(scan_filepath), part_emb)
    
    best_group, confidence, details = classifier.match_image(scan_filepath, os.path.getmtime(scan_filepath), os.path.getsize(scan_filepath))
    # confidence = (0.65 - 0.3) / 0.7 * 100 = 50%
    assert best_group == group_name
    assert abs(confidence - 50.0) < 0.01
