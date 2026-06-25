import os

def generate():
    icons_dir = os.path.dirname(os.path.abspath(__file__))
    svg_files = [f for f in os.listdir(icons_dir) if f.endswith('.svg')]
    svg_files.sort()
    
    html_content = """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Media Keeper - Галерея иконок</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background-color: #121212;
            color: #e0e0e0;
            padding: 40px 20px;
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            margin-bottom: 40px;
            text-align: center;
        }
        h1 {
            font-size: 28px;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 12px;
        }
        h1 span {
            color: #3b82f6;
        }
        p.subtitle {
            color: #888888;
            font-size: 14px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
            gap: 20px;
        }
        .card {
            background-color: #1e1e1e;
            border: 1px solid #2d2d2d;
            border-radius: 12px;
            padding: 24px 16px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            transition: all 0.2s ease;
            height: 190px;
        }
        .card:hover {
            border-color: #3b82f6;
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(59, 130, 246, 0.15);
        }
        .icon-wrapper {
            width: 64px;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: center;
            background-color: #181818;
            border-radius: 8px;
            margin-bottom: 20px;
            border: 1px solid #262626;
            transition: background-color 0.2s ease;
        }
        .card:hover .icon-wrapper {
            background-color: #222;
        }
        .icon-wrapper svg {
            width: 40px;
            height: 40px;
            display: block;
        }
        .copy-btn {
            background-color: #2a2a2a;
            color: #cccccc;
            border: 1px solid #3d3d3d;
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            font-family: inherit;
            font-weight: 500;
            cursor: pointer;
            width: 100%;
            text-align: center;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            transition: all 0.15s ease;
        }
        .copy-btn:hover {
            background-color: #3b82f6;
            color: #ffffff;
            border-color: #3b82f6;
        }
        .copy-btn:active {
            transform: scale(0.97);
        }
        /* Toast notification */
        #toast {
            position: fixed;
            bottom: 24px;
            right: 24px;
            background-color: #3b82f6;
            color: #ffffff;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
            transform: translateY(100px);
            opacity: 0;
            transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
            pointer-events: none;
            z-index: 1000;
        }
        #toast.show {
            transform: translateY(0);
            opacity: 1;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Media Keeper <span>Иконки</span></h1>
            <p class="subtitle">Кликните на название иконки, чтобы скопировать его для использования в коде</p>
        </header>
        
        <div class="grid">
"""
    
    import re
    for filename in svg_files:
        filepath = os.path.join(icons_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            svg_data = f.read()
            
        # Удаляем XML-заголовки
        svg_data = re.sub(r'<\?xml.*?\?>', '', svg_data)
        svg_data = re.sub(r'<!DOCTYPE.*?>', '', svg_data)
        
        # Перекрашиваем currentColor и черный цвет в #dddddd
        svg_data = svg_data.replace('currentColor', '#dddddd')
        svg_data = re.sub(r'stroke=["\'](?:#000000|#000|black)["\']', 'stroke="#dddddd"', svg_data, flags=re.IGNORECASE)
        svg_data = re.sub(r'fill=["\'](?:#000000|#000|black)["\']', 'fill="#dddddd"', svg_data, flags=re.IGNORECASE)
        svg_data = re.sub(r'stroke\s*:\s*(?:#000000|#000|black)', 'stroke: #dddddd', svg_data, flags=re.IGNORECASE)
        svg_data = re.sub(r'fill\s*:\s*(?:#000000|#000|black)', 'fill: #dddddd', svg_data, flags=re.IGNORECASE)
        
        html_content += f"""            <div class="card">
                <div class="icon-wrapper">
                    {svg_data}
                </div>
                <button class="copy-btn" onclick="copyName('{filename}')" title="Нажмите, чтобы скопировать: {filename}">{filename}</button>
            </div>
"""
        
    html_content += """        </div>
    </div>

    <div id="toast">Название скопировано!</div>

    <script>
        function copyName(name) {
            navigator.clipboard.writeText(name).then(() => {
                const toast = document.getElementById('toast');
                toast.textContent = `"${name}" скопировано в буфер!`;
                toast.classList.add('show');
                
                setTimeout(() => {
                    toast.classList.remove('show');
                }, 2000);
            }).catch(err => {
                console.error('Не удалось скопировать текст: ', err);
            });
        }
    </script>
</body>
</html>
"""
    
    output_file = os.path.join(icons_dir, "icons_gallery.html")
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"[Gallery] Generated gallery with {len(svg_files)} icons at: {output_file}")

if __name__ == '__main__':
    generate()
