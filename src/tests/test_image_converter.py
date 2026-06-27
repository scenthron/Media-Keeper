import pytest
from PIL import Image
from modules.editor.image.worker import filter_and_skip_frames, process_single_frame, ImageConverterWorker

def test_filter_and_skip_frames():
    # Создаем фиктивные кадры и задержки
    frames = [object() for _ in range(10)]
    durations = [100] * 10
    
    # 1. Проверяем без пропуска кадров
    res_frames, res_durs = filter_and_skip_frames(frames, durations, skip_enabled=False)
    assert len(res_frames) == 10
    assert len(res_durs) == 10
    assert res_durs == [100] * 10
    
    # 2. Проверяем с пропуском кадров
    res_frames, res_durs = filter_and_skip_frames(frames, durations, skip_enabled=True)
    # Ожидаем, что возьмутся кадры: 0, 2, 4, 6, 8. Всего 5 кадров.
    assert len(res_frames) == 5
    # Длительность каждого оставшегося кадра должна увеличиться вдвое (100 + 100 = 200)
    assert res_durs == [200, 200, 200, 200, 200]

def test_process_single_frame():
    # Создаем простое тестовое изображение 100x100
    img = Image.new('RGB', (100, 100), color='red')
    
    # Настройки
    s_percent = {
        'scale_mode': 'percent',
        'scale_percent': 50
    }
    step_params = {'scale_mul': 1.0}
    
    res = process_single_frame(img, s_percent, step_params)
    assert res.size == (50, 50)
    
    # Настройки пропорции (Fit-In)
    s_prop = {
        'scale_mode': 'proportion',
        'target_w': 80,
        'target_h': 60
    }
    res_prop = process_single_frame(img, s_prop, step_params)
    assert res_prop.size == (60, 60) # Ужато до 60x60, чтобы вписаться в 80x60 по высоте
