from logic_logger import SafeFormatter, PROJECT_ROOT

def test_safe_formatter_anonymize_string():
    # 1. Обычный текст лога без путей должен остаться без изменений
    msg1 = "Асинхронная система логгирования запущена."
    assert SafeFormatter.anonymize_string(msg1) == msg1
    
    # 2. Числа с плавающей точкой и версии не должны ломаться
    msg2 = "Version is v1.0.1 and threshold is 3.14."
    assert SafeFormatter.anonymize_string(msg2) == msg2
    
    # 3. Путь с латиницей и кириллицей на Windows должен маскироваться
    msg3 = "Moving file from C:\\Users\\Centhron\\Downloads\\Идеи.txt to D:\\Media\\Sorted\\video.mp4"
    anon3 = SafeFormatter.anonymize_string(msg3)
    assert "C:\\Iiiii\\Iiiiiiii\\Iiiiiiiii\\Пппп.txt" in anon3
    assert "D:\\Iiiii\\Iiiiii\\iiiii.mp4" in anon3
    
    # 4. Пробелы в путях должны корректно маскироваться, сохраняя разделители ->
    msg4 = "Smart Move Final Failure (C:\\Users\\John Doe\\file.mp4 -> D:\\Dest Folder\\file.mp4): error"
    anon4 = SafeFormatter.anonymize_string(msg4)
    assert "C:\\Iiiii\\Iiii Iii\\iiii.mp4" in anon4
    assert "D:\\Iiii Iiiiii\\iiii.mp4" in anon4
    assert " -> " in anon4
    
    # 5. Одиночный файл с расширением (но не число) должен маскироваться
    msg5 = "Путь: media_keeper.log"
    anon5 = SafeFormatter.anonymize_string(msg5)
    assert "iiiii_iiiiii.log" in anon5
    
    # 6. Относительный путь проекта не должен маскироваться для сохранения читаемости структуры
    msg6 = "Loaded translations from: src/languages/qtbase_ru.qm"
    anon6 = SafeFormatter.anonymize_string(msg6)
    assert "src/languages/qtbase_ru.qm" in anon6
    
    # 7. Трейсбэки исключений должны заменять абсолютный путь проекта на плейсхолдер <PROJECT_ROOT>
    msg7 = f'File "{PROJECT_ROOT}\\src\\main.py", line 123, in <module>'
    anon7 = SafeFormatter.anonymize_string(msg7)
    assert f'File "<PROJECT_ROOT>\\src\\main.py", line 123, in <module>' in anon7
    
    # 8. Сложный путь с пробелами и русскими буквами в кавычках (багфикс утечки пути)
    msg8 = "Native getExistingDirectory returned: 'D:/Ппппппппп D NVME (Взял в мск SSD)/000 Забрал в м1'"
    anon8 = SafeFormatter.anonymize_string(msg8)
    assert "Native getExistingDirectory returned: 'D:/Ппппппппп I IIII (Пппп п ппп III)/000 Пппппп п п0'" in anon8

