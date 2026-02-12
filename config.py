# Конфигурационный файл для HTR Polygon Annotation Tool

import torch

# Параметры устройства для моделей
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# Можно переопределить DEVICE, установив USE_CPU в True
USE_CPU = False  # Установите в True, чтобы принудительно использовать CPU

if USE_CPU:
    DEVICE = 'cpu'

# Параметры моделей
MODEL_PATHS = {
    'yolo': './models/yolo_model.pt',  # Путь к модели YOLOv9
    'trocr': 'microsoft/trocr-base-handwritten'  # Путь к модели TROCR
}