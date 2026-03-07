# Dockerfile для Yat HTR Annotation Tool
# Использует uv для управления зависимостями и CUDA 12.x

FROM pytorch/pytorch:2.4.0-cuda12.4-cudnn9-devel

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Установка uv (Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем зависимости через uv
RUN uv sync --frozen

# Создаем папку для моделей
RUN mkdir -p /app/models

# Файлы приложения не копируются — монтируются через volume в docker-compose.yml
# Это позволяет разрабатывать без пересборки контейнера

EXPOSE 5000

# Используем uv для запуска
CMD ["uv", "run", "python", "app.py"]