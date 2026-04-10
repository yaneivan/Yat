# TODO: Критические проблемы и план исправлений

**Приоритет:** Критические проблемы безопасности и стабильности

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (исправлять СРОЧНО)

### SQLAlchemy сессии в цикле (нет транзакционности)

**Статус:** ❌ Не исправлено
**Приоритет:** 🔴 КРИТИЧНО
**Время на фикс:** 2 часа
**Риск:** Потеря данных при ошибке в batch операциях

**Проблема в `annotation_service.py`:**
```python
def save_annotation(self, filename: str, data: Dict[str, Any]) -> bool:
    session, annotation_repo, image_repo = self._get_session()
    try:
        # ... работа с БД
    finally:
        session.close()  # ← Закрывается после КАЖДОЙ операции
```

**В batch операции (50 изображений):**
- 50 × открытие сессии
- 50 × закрытие сессии
- **Нет транзакционности** — если ошибка на 49-м, первые 48 уже закоммичены

**Решение:**
```python
def save_batch_annotations(self, annotations: List[Dict]):
    session = SessionLocal()
    try:
        for annotation in annotations:
            # ... сохранить
        session.commit()  # ← Один коммит на все
    except:
        session.rollback()  # ← Откат всех
    finally:
        session.close()
```

**Файлы для изменения:**
- `services/annotation_service.py` (добавить batch метод)
- `logic.py` (вызывать batch метод вместо одиночных)

---

### 5. Утечка памяти в recognition_progress

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟡 СЕРЬЁЗНО  
**Время на фикс:** 1 час  
**Риск:** Out of Memory при большой нагрузке

**Проблема в `app.py`:**
```python
# Глобальный dict
recognition_progress = {}

@app.route('/api/recognize_text', methods=['POST'])
def recognize_text():
    recognition_progress[validated] = {...}  # ← Запись
    
    def task():
        try:
            ai_service.recognize_text(...)
        finally:
            time.sleep(5)  # ← 5 секунд перед очисткой
            if validated in recognition_progress:
                del recognition_progress[validated]
```

**Проблема:**
- Если ошибка перед `finally` — запись остаётся навсегда
- 100 пользователей = 100 записей в памяти
- Нет ограничения размера dict

**Решение:**
```python
from collections import OrderedDict
from datetime import datetime, timedelta

class ProgressTracker:
    def __init__(self, max_size=1000, ttl_minutes=10):
        self._data = OrderedDict()
        self._max_size = max_size
        self._ttl = timedelta(minutes=ttl_minutes)
    
    def set(self, key, value):
        self._cleanup()
        self._data[key] = {'value': value, 'time': datetime.now()}
    
    def get(self, key, default=None):
        if key in self._data:
            return self._data[key]['value']
        return default
    
    def __contains__(self, key):
        return key in self._data
    
    def __delitem__(self, key):
        del self._data[key]
    
    def _cleanup(self):
        now = datetime.now()
        # Удалить старые записи
        for key in list(self._data.keys()):
            if now - self._data[key]['time'] > self._ttl:
                del self._data[key]
        # Удалить лишние
        while len(self._data) > self._max_size:
            self._data.popitem(last=False)

recognition_progress = ProgressTracker()
```

**Файлы для изменения:**
- `app.py`

---

## 🟠 СРЕДНИЕ ПРОБЛЕМЫ (исправлять в ближайшем спринте)

### 5. Console.log в production

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 30 минут
**Риск:** Замедление, утечка информации

**Проблема:**

Найдено 32 `console.log` в JS файлах:

| Файл | Количество |
|------|------------|
| `static/js/project_manager.js` | 14 |
| `static/js/editor.js` | 4 |
| `static/js/text_editor.js` | 14 |

**Пример:**
```javascript
console.log('User role:', this.userRole);
console.log('Creating project:', name, description);
console.log('Polygon clicked directly - index:', obj.index);
```

**Решение:**

```javascript
// Удалить все console.log или использовать условный логгер
const DEBUG = false;
const log = DEBUG ? console.log : () => {};
log('Debug message');  // Не выполняется в production
```

**Файлы для изменения:**
- `static/js/project_manager.js`
- `static/js/editor.js`
- `static/js/text_editor.js`

---

### 6. Дублирование кода

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 45 минут
**Риск:** Поддерживаемость кода

**Проблема:**

1. **CSRF функции** дублируются в 6 местах:
   - `static/js/api.js` (getCsrfToken, getCsrfHeaders) — ✅ централизовано
   - `static/js/project_manager.js` (дубликат функций) — ⚠️ нужно удалить
   - `static/js/editor.js` (прямой fetch с получением из meta) — ⚠️ нужно использовать API
   - `static/js/text_editor.js` (прямой fetch с получением из meta) — ⚠️ нужно использовать API
   - `templates/project.html` (6 inline fetch с получением из meta) — ⚠️ нужно использовать API
   - `templates/cropper.html` (прямой fetch с получением из meta) — ⚠️ нужно использовать API

2. **`_validate_filename()`** дублируется в сервисах:
   - `services/annotation_service.py`
   - `services/image_service.py`

**Решение:**

```javascript
// 1. Оставить getCsrfToken/getCsrfHeaders только в api.js
// 2. Удалить дубликаты из project_manager.js
// 3. Добавить в api.js недостающие методы:
API.detectLines(filename, projectName)      // /api/detect_lines
API.recognizeText(filename, regions, projectName)  // /api/recognize_text
API.recognizeProgress(filename)             // /api/recognize_progress/<filename>
API.crop(filename, box, projectName)        // /api/crop
API.exportPdf(projectName, variant)         // /api/projects/<name>/export_pdf
API.exportZip(projectName)                  // /api/projects/<name>/export_zip
API.importZip(formData, projectName)        // /api/import_zip

// 4. Обновить все файлы чтобы использовали API.* вместо прямых fetch
```

```python
# services/utils.py
import re

VALID_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\u0400-\u04FF]+\.[a-zA-Z0-9]+$')

def validate_filename(filename: str) -> str:
    if not filename:
        raise ValueError("Filename cannot be empty")
    if '..' in filename or '/' in filename or '\\' in filename:
        raise ValueError("Invalid filename: path traversal detected")
    if not VALID_FILENAME_PATTERN.match(filename):
        return re.sub(r'[<>:"|?*]', '_', filename)
    return filename
```

**Файлы для изменения:**
- `static/js/project_manager.js` (удалить дубликаты, импортировать из api.js)
- `services/utils.py` (создать)
- `services/annotation_service.py`
- `services/image_service.py`

---

### 8. Текст в модалках не автосохраняется

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟠 СРЕДНЕ  
**Время на фикс:** 1 час  
**Риск:** Потеря данных пользователя при закрытии браузера

**Проблема:**
```javascript
// text_editor.js
openTextModal(index) {
    const text = this.texts[index] || '';
    // Пользователь вводит текст
    // Если закроет браузер — текст потерян
}
```

**Решение:**
```javascript
// Debounce автосохранение
let autoSaveTimer;
input.addEventListener('input', () => {
    clearTimeout(autoSaveTimer);
    autoSaveTimer = setTimeout(() => {
        API.saveText(this.filename, index, input.value);
    }, 2000);
});
```

**Файлы для изменения:**
- `static/js/text_editor.js`
- `app.py` (добавить endpoint /api/save_text)

---

### 6. Нет индикатора загрузки модели

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟠 СРЕДНЕ  
**Время на фикс:** 2 часа  
**Риск:** Плохой UX — пользователь ждёт 5 минут без обратной связи

**Проблема:**
```python
# app.py
if ai_service.is_trocr_available():
    ai_service.initialize_models(...)  # ← 2-5 минут загрузки
    # Пользователь не видит прогресс
```

**Решение:**
```python
# WebSocket для прогресса
@socketio.on('connect')
def on_connect():
    emit('model_loading', {'progress': 0})

def load_model():
    for progress in load_progress():
        emit('model_loading', {'progress': progress})
```

**Файлы для изменения:**
- `app.py` (добавить Flask-SocketIO)
- `templates/index.html` (добавить индикатор)
- `static/js/dashboard.js` (отображение прогресса)

---

## 🟢 МЕЛКИЕ ПРОБЛЕМЫ (исправлять по желанию)

### 7. Хардкод путей

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟢 МЕЛКО  
**Время на фикс:** 30 минут

**Проблема:**
```python
# config.py
MODEL_PATHS = {
    'yolo': './models/yolo_model.pt',  # ← Хардкод
}
```

**Решение:** Использовать `pathlib.Path` и env variables

**Файлы для изменения:**
- `config.py`

---

### 9. Magic numbers

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 МЕЛКО
**Время на фикс:** 30 минут

**Проблема:**
```python
# editor.js
this.snapDist = 15;  // ← Почему 15?
this.maxHistory = 50;  // ← Почему 50?
```

**Решение:** Вынести в константы с комментариями

**Файлы для изменения:**
- `static/js/editor.js`
- `static/js/text_editor.js`

---

### 10. Сложные функции (>50 строк)

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 МЕЛКО
**Время на фикс:** 4 часа
**Риск:** Сложность поддержки и тестирования

**Проблема:**

Найдено 12 функций >50 строк:

| Файл | Функция | Строк |
|------|---------|-------|
| `logic.py` | `process_zip_import()` | 85 |
| `services/image_service.py` | `crop_image()` | 82 |
| `services/pdf_export_service.py` | `export_parallel()` | 98 |
| `static/js/editor.js` | `setupCanvasEvents()` | 150+ |
| `static/js/text_editor.js` | `loadTextData()` | 80+ |

**Решение:** Рефакторинг — разбить на подфункции

**Файлы для изменения:**
- `logic.py`
- `services/image_service.py`
- `services/pdf_export_service.py`
- `static/js/editor.js`
- `static/js/text_editor.js`

---

### 11. Нет breadcrumb навигации

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 МЕЛКО
**Время на фикс:** 30 минут
**Риск:** Плохой UX — пользователь не видит текущий путь

**Проблема:**

Нет индикации пути (Проекты → Проект X → Изображение Y)

**Решение:**

```html
<div class="breadcrumb">
    <a href="/">Проекты</a> → 
    <a href="/project/{{ project }}">{{ project }}</a> → 
    <span>{{ filename }}</span>
</div>
```

**Файлы для изменения:**
- `templates/editor.html`
- `templates/cropper.html`
- `templates/text_editor.html`

---

### 12. Нет кэширования часто читаемых данных

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 МЕЛКО
**Время на фикс:** 1.5 часа
**Риск:** Лишние запросы к БД

**Проблема:**

`get_all_projects()` и `get_all_images()` вызываются на каждой странице без кэша

**Решение:**

```python
from functools import lru_cache
import time

class ProjectService:
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 60  # секунд

    def get_all_projects(self) -> List[Dict[str, Any]]:
        if 'projects' in self._cache:
            cached_time, data = self._cache['projects']
            if time.time() - cached_time < self._cache_ttl:
                return data
        
        data = self._load_projects_from_db()
        self._cache['projects'] = (time.time(), data)
        return data
```

**Файлы для изменения:**
- `services/project_service.py`
- `services/image_service.py`

---

## 📋 ПЛАН ДЕЙСТВИЙ

### СРОЧНО (сегодня)

- [ ] Исправить сессии в batch операциях (транзакционность)

### В ЭТОЙ НЕДЕЛЕ 📅

- [ ] Починить утечку памяти в `recognition_progress`
- [ ] Добавить валидацию входных данных

### В СЛЕДУЮЩЕМ СПРИНТЕ 📆

- [ ] Автосохранение текста
- [ ] Индикатор загрузки моделей

### ПО ЖЕЛАНИЮ 🕐

- [ ] Убрать хардкод путей
- [ ] Добавить тесты AI
- [ ] Убрать magic numbers
- [ ] Копирование изображения
- [ ] Унификация фоновых задач
- [ ] Ленивая инициализация TROCR
- [ ] Исправление математики координат
- [ ] Переименовать статус "Размечено" → "Добавлены полигоны"

---

## 🔧 НОВЫЕ ЗАДАЧИ (от пользователя)

---

## 📝 ЗАМЕЧАНИЯ

### ImageStatus: enum vs строка

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 НИЗКОЕ
**Время на фикс:** 2 часа

**Проблема:**
`Image.status` хранится как `String(50)` с `.value`, но в коде хаос:

```python
# models.py — строка
status = Column(String(50), default=ImageStatus.UPLOADED.value)

# logic.py:646 — передаётся enum объект ❌
status=ImageStatus.SEGMENTED,

# annotation_service.py — сравнение со строкой ✅
if image.status == ImageStatus.RECOGNIZED.value:
```

**Что сделать:**
1. Вариант А: `Column(ImageStatus)` — SQLAlchemy Enum
2. Вариант Б: Оставить строку, убрать `.value` из сравнений, унифицировать логику
3. Миграция БД если нужен вариант А

**Файлы для изменения:**
- `database/models.py`
- `services/image_service.py`
- `services/annotation_service.py`
- `logic.py`

---

### Зависимости для добавления

```toml
# pyproject.toml
[project]
dependencies = [
    "marshmallow>=3.20.0",   # Валидация данных
    "flask-socketio>=5.3.0", # WebSocket для прогресса
]
```

### Тестирование после исправлений

1. **Batch операции:** Прервать на середине и проверить откат
2. **Память:** Создать 100+ задач и проверить утечки
3. **Валидация:** Попытаться отправить некорректные данные

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-19)

### 11. Копирование изображения региона

**Статус:** ❌ Не исправлено
**Приоритет:** 🟢 МЕЛКО
**Время на фикс:** 30 минут

**Описание:**
Кнопка "Копировать изображение" в модальном окне ввода текста.
Копирует изображение региона в буфер обмена для отправки в чат.

**Требования:**
- Вырезать регион из изображения (с padding ~50px)
- Конвертировать в PNG Blob
- Записать в clipboard через `navigator.clipboard.write()`
- Показать уведомление "Скопировано!"

**Файлы для изменения:**
- `templates/text_editor.html` (кнопка копирования)
- `static/js/text_editor.js` (copyRegionToClipboard)

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-20)

### 12. Унификация фоновых задач на task_service

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 3 часа

**Описание:**
Сейчас в проекте два разных механизма для фоновых задач:
1. `task_service` — правильный, с сохранением в БД (batch операции)
2. `threading.Thread` + global dict — устаревший (crop, recognize_text)

**Проблемы:**
- `/api/crop` — нет отслеживания прогресса, нет task_id
- `/api/recognize_text` — global dict `recognition_progress` (утечка памяти)
- Нет единого API для мониторинга задач

**Решение:**
- Переделать `/api/crop` на `task_service.run_background()`
- Переделать `/api/recognize_text` на `task_service.run_background()`
- Удалить global dict `recognition_progress`
- Все задачи хранятся в БД через `TaskRepository`

**Файлы для изменения:**
- `app.py` (endpoint'ы crop и recognize_text)
- `services/image_service.py` (crop_image — вернуть прогресс)
- `services/ai_service.py` (recognize_text — использовать progress_callback)

---

### 13. Ленивая инициализация TROCR

**Статус:** ❌ Не исправлено
**Приоритет:** 🟡 НИЗКОЕ
**Время на фикс:** 1 час

**Описание:**
Сейчас TROCR загружается при старте приложения (~2-5 минут).
Можно сделать ленивую загрузку — при первом запросе.

**Текущее поведение:**
```python
# app.py:43-48
if ai_service.is_trocr_available():
    ai_service.initialize_models("raxtemur/trocr-base-ru")  # ← При старте
```

**Преимущества ленивой инициализации:**
- Быстрый старт приложения
- Не занимает память если не используется
- Модель загружается только когда нужна

**Недостатки:**
- Первый запрос на распознавание медленный
- Ошибка обнаружится при использовании, а не при старте

**Решение:**
- Убрать вызов `initialize_models()` из `app.py`
- В `ai_service._get_trocr_model()` сделать lazy init (как для YOLO)
- Добавить метод `ai_service.is_trocr_initialized()` для проверки

**Файлы для изменения:**
- `app.py` (убрать инициализацию при старте)
- `services/ai_service.py` (ленивая загрузка TROCR)

---

### 14. Исправление математики координат

**Статус:** ❌ Не исправлено
**Приоритет:** 🔴 КРИТИЧНО
**Время на фикс:** 4 часа

**Описание:**
В `logic.py` есть проблемы с пересчётом координат полигонов.

**Проблемы:**

1. **`recalculate_regions()` — DRIFT BUG**
   - Неправильное обратное преобразование при поворотах
   - Работает только для небольших углов
   - При ре-кропе с поворотом полигоны "уплывают"

2. **`calculate_overlap_ratio()` — приближение**
   - Использует bounding box вместо пересечения полигонов
   - Может давать ложные срабатывания для сложных форм

3. **`merge_overlapping_regions()` — жадный алгоритм**
   - Порядок влияет на результат
   - Недетерминированное поведение

**Решение:**
- Переписать `recalculate_regions()` с правильной обратной билинейной интерполяцией
- Заменить `calculate_overlap_ratio()` на точное пересечение (shapely или Sutherland-Hodgman)
- Опционально: улучшить `merge_overlapping_regions()` на non-greedy алгоритм

**Файлы для изменения:**
- `logic.py` (recalculate_regions, calculate_overlap_ratio)
- `pyproject.toml` (опционально: добавить shapely)

**✅ ПРИМЕЧАНИЕ:** `shapely>=2.0.0` уже добавлена в `pyproject.toml:12` и используется в `simplify_points()` (Ramer-Douglas-Peucker)

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-22)

### 15. Тестирование и доработка переключения статусов

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 2 часа

**Описание:**
После переименования статусов нужно проверить и улучшить логику автоматического переключения.

**Что проверить:**
1. **После распознавания текста (AI)** — меняется ли статус на «Текст распознан»?
   - Endpoint: `/api/recognize_text`
   - Файл: `services/ai_service.py` — `recognize_text()`
   
2. **После рисования полигонов** — меняется ли статус на «Полигоны готовы»?
   - Endpoint: `/api/save`
   - Файл: `app.py` — `save_data()`
   
3. **После обрезки** — меняется ли статус на «Обрезано»?
   - Endpoint: `/api/crop`
   - Файл: `services/image_service.py` — `crop_image()`

**Возможные улучшения:**
- Добавить автоматическое переключение статусов при действиях пользователя
- Убрать ручное переключение через popover (сделать только для ревью)
- Добавить уведомления при автоматическом переключении

**Файлы для проверки:**
- `app.py` (endpoint'ы save, crop, recognize_text)
- `services/ai_service.py` (recognize_text — статус после распознавания)
- `services/image_service.py` (crop_image — статус после обрезки)
- `services/annotation_service.py` (save_annotation — логика статусов)
- `static/js/editor.js` (сохранение полигонов)
- `static/js/text_editor.js` (сохранение текста)

**Критерии приёмки:**
- [ ] Статус меняется автоматически после каждого действия
- [ ] Ручное переключение через popover работает
- [ ] В popover только актуальные статусы (5 шт.)
- [ ] Нет ошибок при переключении

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-24)

### 17. Вынос CSS из HTML в единый файл

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 2 часа

**Описание:**
Сейчас CSS дублируется в 4 местах, что создаёт проблемы поддержки и вызывает FOUC (Flash of Unstyled Content).

**Проблема:**

| Файл | Inline CSS | Строк |
|------|------------|-------|
| `static/css/style.css` | ✅ Основной файл | 572 |
| `templates/index.html` | ❌ `<style>` в head | ~200 |
| `templates/text_editor.html` | ❌ `<style>` в head | ~250 |
| `templates/cropper.html` | ❌ `<style>` в head | ~100 |
| `templates/editor.html` | ❌ `<style>` в head | ~150 |

**Последствия:**
1. **Дублирование кода** — при изменении стиля нужно править 5 файлов
2. **FOUC** — браузер показывает нестилизованную страницу до загрузки inline стилей
3. **Кэш не работает** — CSS в HTML не кэшируется отдельно
4. **Увеличенный размер** — одни и те же стили загружаются 5 раз

**Решение:**

**Шаг 1: Создать структуру**
```
static/css/
├── style.css           # Основные стили (уже есть)
├── editors.css         # Стили редакторов (новый)
└── dashboard.css       # Стили dashboard (новый)
```

**Шаг 2: Вынести стили из HTML**

```html
<!-- Было: templates/text_editor.html -->
<head>
    <style>
        body { margin: 0; font-family: 'Segoe UI', sans-serif; ... }
        #toolbar { height: 50px; background: #333; ... }
        /* 250 строк стилей */
    </style>
</head>

<!-- Стало: templates/text_editor.html -->
<head>
    <link rel="stylesheet" href="/static/css/style.css">
    <link rel="stylesheet" href="/static/css/editors.css">
</head>
```

**Шаг 3: Обновить все шаблоны**

| Шаблон | Куда вынести |
|--------|--------------|
| `index.html` | `dashboard.css` |
| `editor.html` | `editors.css` |
| `text_editor.html` | `editors.css` |
| `cropper.html` | `editors.css` |
| `project.html` | `dashboard.css` |
| `login.html` | `auth.css` (опционально) |

**Шаг 4: Удалить дубликаты**

После выноса удалить повторяющиеся стили:
- `body` — оставить только в `style.css`
- `.btn` — оставить только в `style.css`
- `#toolbar` — объединить из 3 файлов

**Файлы для изменения:**
- `static/css/editors.css` (создать)
- `static/css/dashboard.css` (создать)
- `templates/*.html` (удалить `<style>`, добавить `<link>`)

**Критерии приёмки:**
- [ ] Нет inline `<style>` в HTML (кроме критических)
- [ ] Все стили в отдельных `.css` файлах
- [ ] Нет дублирования стилей
- [ ] FOUC исчез
- [ ] Размер HTML уменьшился на ~700 строк

**Ветка:** `feature/extract-css`

---

### 18. Фронтенд: рефакторинг и улучшение архитектуры

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 8 часов

**Описание:**
Провести полный рефакторинг фронтенда для улучшения архитектуры, производительности и поддерживаемости.

**Найденные проблемы (аудит от 2026-03-24):**

#### 18.1. Console.log в production (13 штук)

**Файлы:**
- `static/js/text_editor.js` (6 штук)
- `static/js/editor.js` (2 штуки)
- `static/js/project_manager.js` (5 штук)

**Решение:**
```javascript
// Заменить на debug-утилиту
const DEBUG = false;
const log = DEBUG ? console.log : () => {};
log('Debug message');
```

#### 18.2. Отсутствие обработки ошибок в api.js

**Проблема:**
```javascript
async listImages() {
    const res = await fetch('/api/images_list');
    return res.json();  // ❌ Нет проверки res.ok
}
```

**Решение:**
```javascript
async listImages() {
    const res = await fetch('/api/images_list');
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
}
```

#### 18.3. Магические числа

**Проблема:**
```javascript
this.snapDist = 15;           // Почему 15?
this.maxHistory = 50;         // Почему 50?
setTimeout(checkStatus, 1000); // Почему 1000ms?
```

**Решение:**
```javascript
const CONFIG = {
    SNAP_DISTANCE: 15,
    MAX_HISTORY: 50,
    POLL_INTERVAL: 1000,
    FONT_SIZE: { MIN: 12, MAX: 60 }
};
```

#### 18.4. Нет debounce/throttle

**Проблема:**
```javascript
searchInput.addEventListener('input', () => {
    this.renderProjects();  // ← Перерисовка при каждом нажатии
});
```

**Решение:**
```javascript
const debouncedRender = debounce(() => this.renderProjects(), 300);
searchInput.addEventListener('input', debouncedRender);
```

#### 18.5. Нет индикаторов загрузки

**Проблема:** Пользователь не видит что данные грузятся.

**Решение:**
```javascript
async loadProjects() {
    this.showLoading(true);
    try {
        this.projects = await ProjectAPI.getProjects();
    } finally {
        this.showLoading(false);
    }
}
```

#### 18.6. Дублирование: editor.js ↔ text_editor.js

**Оба файла имеют:**
- `HistoryManager` (одинаковый код)
- `goImage()` (похожая логика)
- `saveData()` (разная реализация)
- Обработка canvas событий

**Решение:** Создать базовый класс `BaseEditor`.

**Файлы для изменения:**
- `static/js/api.js` (обработка ошибок)
- `static/js/core/` (создать: base_editor.js, config.js, utils.js)
- `static/js/editor.js` (рефакторинг)
- `static/js/text_editor.js` (рефакторинг)
- `static/js/project_manager.js` (debounce, индикаторы)
- Все JS файлы (удалить console.log)

**Ветка:** `feature/frontend-refactor`

---

## 📋 ЗАДАЧИ В РАБОТЕ

---

### 17. Вынос CSS из HTML в единый файл

**Статус:** 🟡 В ПРОЦЕССЕ
**Ветка:** `feature/extract-css`

---

### 16. Улучшение AI Service: батчинг, очередь, выгрузка моделей

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 4 часа

**Описание:**
Сейчас AI Service (`services/ai_service.py`) имеет базовую реализацию с синглтоном и lazy initialization.
Однако отсутствуют важные функции для production-нагрузки:

**Текущее состояние:**
- ✅ Синглтон (`ai_service = AIService()`)
- ✅ Lazy initialization моделей
- ✅ Thread-safe (double-checked locking)
- ✅ Кэширование моделей (не выгружаются)

**Проблемы:**
1. **Нет реального батчинга** — пакетная обработка вызывает YOLO по одной картинке в цикле
2. **Нет очереди задач** — `logic.py` напрямую вызывает `ai_service.detect_lines()`
3. **Нет выгрузки моделей** — модели занимают RAM/GPU постоянно
4. **Прогресс в `logic.py`** — AI service не управляет прогрессом выполнения

**Сценарии использования:**

| Сценарий | Где вызывается | Как сейчас | Проблема |
|----------|----------------|------------|----------|
| **Одиночный запрос** (из редактора) | `editor.js` → `/api/detect_lines` | Синхронно, браузер ждёт | ✅ Нормально для интерактива |
| **Пакетный запрос** (из project.html) | `project_manager.js` → `/api/batch_detect` | Цикл по одной картинке | ❌ Нет GPU батчинга |

**Производительность (оценка):**

| Количество картинок | Сейчас (по одной) | С батчингом |
|---------------------|-------------------|-------------|
| 1 | ~2 сек | ~2 сек |
| 10 | ~20 сек | ~5-7 сек |
| 100 | ~200 сек | ~30-50 сек |

---

### Задачи для реализации

#### 16.1. Добавить пакетную обработку для YOLO

**Файл:** `services/ai_service.py`

**Задача:** Создать метод `detect_lines_batch()` для реальной пакетной обработки на GPU.

```python
def detect_lines_batch(
    self,
    image_paths: List[str],
    settings: Dict[str, Any],
    progress_callback: Callable = None
) -> Dict[str, List[Dict]]:
    """
    Пакетная детекция на нескольких изображениях.
    
    Args:
        image_paths: Список путей к изображениям
        settings: Настройки детекции (threshold, simplification, merge)
        progress_callback: Callback(processed, total)
    
    Returns:
        Dict: {filename: [regions]}
    """
    # Загрузить все изображения
    images = [Image.open(path) for path in image_paths]
    
    # ОДИН вызов модели на все изображения (GPU батчинг!)
    model = self._get_yolo_model()
    results = model(images, conf=settings.get('threshold', 50)/100)
    
    # Обработать результаты
    output = {}
    for idx, result in enumerate(results):
        filename = os.path.basename(image_paths[idx])
        regions = self._process_result(result, settings)
        output[filename] = regions
        
        if progress_callback:
            progress_callback(idx + 1, len(images))
    
    return output
```

**Преимущества:**
- 3-4x быстрее на GPU (параллелизм внутри YOLO)
- Меньше накладных расходов на загрузку изображений

**Где использовать:**
- `logic.py:run_batch_detection_for_project()` — вместо цикла по одной

---

#### 16.2. Добавить выгрузку моделей

**Файл:** `services/ai_service.py`

**Задача:** Создать метод `unload_models()` для освобождения памяти.

```python
def unload_models(self):
    """
    Выгрузить модели из памяти (освободить GPU RAM).
    
    Вызывать:
    - При длительном простое (>5 мин)
    - Перед завершением приложения
    - Для экономии памяти на серверах с несколькими сервисами
    """
    import gc
    
    if self._yolo_model:
        del self._yolo_model
        self._yolo_model = None
    
    if self._trocr_model:
        del self._trocr_model
        self._trocr_model = None
        self._trocr_processor = None
    
    gc.collect()
    torch.cuda.empty_cache()
    self._models_initialized = False
```

**Дополнительно:** Добавить автоматическую выгрузку при простое.

```python
# В __init__
self._last_activity = time.time()
self._idle_timeout = 300  # 5 минут

# В detect_lines() и recognize_text()
self._last_activity = time.time()

# В фоновом потоке
def _check_idle():
    if time.time() - self._last_activity > self._idle_timeout:
        self.unload_models()
```

---

#### 16.3. Перенести управление прогрессом в AI Service

**Файл:** `services/ai_service.py`

**Проблема:** Сейчас `logic.py` управляет прогрессом через `task_service.update_progress()`.

**Решение:** AI service должен принимать callback для обновления прогресса.

**Сейчас:**
```python
# logic.py:675-690
for idx, image_name in enumerate(image_names):
    regions = ai_service.detect_lines(image_name, settings)
    annotation_service.save_annotation(...)
    task_service.update_progress(task.id, idx + 1)  # ← logic.py знает о прогрессе
```

**Как должно быть:**
```python
# logic.py
def run_batch_detection_for_project(project_name, settings, task_id):
    images = project_service.get_images(project_name)
    
    def on_progress(processed, total):
        task_service.update_progress(task.id, processed)
    
    ai_service.detect_lines_batch(
        image_paths=[img.cropped_path for img in images],
        settings=settings,
        progress_callback=on_progress  # ← AI service управляет прогрессом
    )
```

---

#### 16.4. Добавить очередь задач (опционально)

**Файл:** `services/ai_service.py` или новый `services/ai_queue.py`

**Задача:** Создать очередь для управления приоритетами и предотвращения перегрузки.

```python
from queue import PriorityQueue
from dataclasses import dataclass, field
from enum import Enum

class TaskPriority(Enum):
    HIGH = 1      # Одиночные запросы из редактора
    NORMAL = 5    # Пакетная обработка
    LOW = 10      # Фоновые задачи

@dataclass(order=True)
class AITask:
    priority: int
    created_at: float = field(compare=False)
    func: str = field(compare=False)  # 'detect' или 'recognize'
    args: tuple = field(compare=False)
    kwargs: dict = field(compare=False)
    callback: callable = field(compare=False, default=None)

class AIQueue:
    def __init__(self, max_workers=2):
        self._queue = PriorityQueue()
        self._workers = []
        self._shutdown = False
        self._max_workers = max_workers
    
    def submit(self, func, args, kwargs, callback, priority=TaskPriority.NORMAL):
        self._queue.put(AITask(
            priority=priority.value,
            created_at=time.time(),
            func=func,
            args=args,
            kwargs=kwargs,
            callback=callback
        ))
    
    def start(self):
        for _ in range(self._max_workers):
            worker = threading.Thread(target=self._worker_loop, daemon=True)
            worker.start()
            self._workers.append(worker)
    
    def _worker_loop(self):
        while not self._shutdown:
            try:
                task = self._queue.get(timeout=1)
                result = getattr(ai_service, task.func)(*task.args, **task.kwargs)
                if task.callback:
                    task.callback(result)
            except queue.Empty:
                continue
```

**Где использовать:**
- `app.py:detect_lines()` — `priority=HIGH` (интерактивный запрос)
- `app.py:batch_detect()` — `priority=NORMAL` (фоновая задача)

---

#### 16.5. Обновить `logic.py` для использования батчинга

**Файл:** `logic.py`

**Задача:** Заменить цикл на вызов `detect_lines_batch()`.

**Сейчас:**
```python
def run_batch_detection_for_project(project_name, settings, task_id):
    images = project_service.get_images(project_name)
    
    for idx, image_name in enumerate(image_names):
        regions = ai_service.detect_lines(image_name, settings)  # ← По одной!
        annotation_data = annotation_service.get_annotation(...)
        annotation_data['regions'] = regions
        annotation_service.save_annotation(...)
        task_service.update_progress(task.id, idx + 1)
```

**Как должно быть:**
```python
def run_batch_detection_for_project(project_name, settings, task_id):
    images = project_service.get_images(project_name)
    image_paths = [img.cropped_path for img in images]
    
    def on_progress(processed, total):
        task_service.update_progress(task.id, processed)
    
    # ← Пакетная обработка
    results = ai_service.detect_lines_batch(
        image_paths=image_paths,
        settings=settings,
        progress_callback=on_progress
    )
    
    # Сохранить результаты
    for image in images:
        filename = image.filename
        if filename in results:
            annotation_data = annotation_service.get_annotation(filename, project_name)
            annotation_data['regions'] = results[filename]
            annotation_data['status'] = ImageStatus.SEGMENTED.value
            annotation_service.save_annotation(filename, annotation_data, project_name)
```

---

**Ожидаемые улучшения:**

| Метрика | Сейчас | После |
|---------|--------|-------|
| 10 картинок (детекция) | ~20 сек | ~5-7 сек |
| 100 картинок (детекция) | ~200 сек | ~30-50 сек |
| RAM (после обработки) | Занята постоянно | Освобождается через 5 мин |
| GPU RAM | Занята постоянно | Освобождается при простое |
| Приоритеты | Нет | Есть (интерактив > фон) |

---

**Приоритет задач:**
1. **Высокий:** Добавить `detect_lines_batch()` — 3-4x ускорение
2. **Средний:** Добавить `unload_models()` — экономия памяти
3. **Низкий:** Очередь задач — улучшение архитектуры
4. **Низкий:** Перенос прогресса в AI service — рефакторинг

---

**Файлы для изменения:**
- `services/ai_service.py` — основная реализация
- `services/ai_queue.py` — новый файл (опционально)
- `logic.py` — использование батчинга
- `app.py` — endpoint'ы для одиночных и пакетных запросов
- `config.py` — настройки (idle_timeout, max_workers)

---

**Критерии приёмки:**
- [ ] `detect_lines_batch()` обрабатывает пакет изображений за один вызов YOLO
- [ ] `unload_models()` освобождает GPU RAM
- [ ] Прогресс обновляется через callback из AI service
- [ ] Пакетная обработка 10 изображений работает в 3x быстрее
- [ ] Модели выгружаются после 5 минут простоя

