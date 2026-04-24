# Конфигурационный файл для HTR Polygon Annotation Tool

import os
import torch
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Параметры устройства для моделей
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'

# Можно переопределить DEVICE, установив USE_CPU в True
USE_CPU = False  # Установите в True, чтобы принудительно использовать CPU

if USE_CPU:
    DEVICE = 'cpu'

# Параметры моделей
MODEL_PATHS = {
    'yolo': './models/model.pt',      # Путь к модели YOLOv9
    'trocr': 'raxtemur/trocr-base-ru'       # HuggingFace модель TROCR (русская версия)
}

# Пароль для создания первого админа при старте (seed)
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')

# Включить систему аутентификации (true/false)
# Если false — открытый доступ без логина, все пользователи admin
ENABLE_AUTH = os.environ.get('ENABLE_AUTH', 'false').lower() == 'true'