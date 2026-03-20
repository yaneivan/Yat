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
    'yolo': './models/yolo_model.pt',  # Путь к модели YOLOv9
    'trocr': 'microsoft/trocr-base-handwritten'  # Путь к модели TROCR
}

# Пароли для доступа
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
USER_PASSWORD = os.environ.get('USER_PASSWORD')

# Проверка корректности конфигурации
# Только два режима:
# 1. Оба пароля не заданы → открытый доступ (все admin)
# 2. Оба пароля заданы → разделение на admin/user
# Частичное задание → ошибка
if (ADMIN_PASSWORD is None) != (USER_PASSWORD is None):
    raise ValueError(
        "Некорректная конфигурация паролей.\n"
        "Доступны только два режима:\n"
        "1. Без паролей (оба не заданы) → открытый доступ, все пользователи admin\n"
        "2. Оба пароля заданы → разделение на admin и user\n\n"
        f"Текущее состояние:\n"
        f"  ADMIN_PASSWORD: {'задан' if ADMIN_PASSWORD else 'не задан'}\n"
        f"  USER_PASSWORD: {'задан' if USER_PASSWORD else 'не задан'}"
    )

# Флаг: используется ли система с разделением прав
USE_ROLE_BASED_AUTH = ADMIN_PASSWORD is not None and USER_PASSWORD is not None