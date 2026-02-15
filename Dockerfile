FROM pytorch/pytorch:2.0.0-cuda11.7-cudnn8-devel

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && apt-get install -y \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Установка зависимостей
RUN pip install --no-cache-dir transformers==4.44.0 numpy==1.24.3 ultralytics

# Создаем папку для моделей
RUN mkdir -p /app/models

# Копируем и устанавливаем зависимости
COPY requirements.txt .
RUN pip install -r requirements.txt

# Копируем остальные файлы
COPY app.py config.py logic.py storage.py ./

EXPOSE 5000

CMD ["python", "app.py"]