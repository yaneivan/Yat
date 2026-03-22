# TODO: Критические проблемы и план исправлений

**Приоритет:** Критические проблемы безопасности и стабильности

---

## ✅ ВЫПОЛНЕНО (2026-03-22)

### Очистка кода и тесты

- [x] Удалить неиспользуемые импорты (argparse, traceback, inch, canvas, TA_LEFT, timedelta, TaskModel)
- [x] Исправить ai_service.py для использования config.MODEL_PATHS
- [x] Разделить тесты на быстрые (test_api.py, AI замокан) и медленные (test_ai.py, реальный AI)
- [x] Создать conftest.py с фикстурами для тестов
- [x] Добавить temporary database для тестов чтобы не удаляли основную БД
- [x] Отключить CSRF для тестов через app.config['WTF_CSRF_ENABLED'] = False
- [x] Перенести тесты AI из test_services.py в test_ai.py

---

## 🔧 ТЕКУЩИЙ ПРОГРЕСС (в работе)

### Очистка кода от мёртвого кода

**Статус:** 🟡 В ПРОЦЕССЕ
**Дата начала:** 2026-03-22

**Что сделано:**
- Удалены неиспользуемые импорты (argparse, traceback, inch, canvas, TA_LEFT, timedelta, TaskModel)
- Исправлен ai_service.py для использования config.MODEL_PATHS
- Разделены тесты на быстрые (test_api.py) и медленные (test_ai.py)
- Создан conftest.py с фикстурами
- Перенесены AI тесты из test_services.py в test_ai.py

**Что осталось сделать:**
- [ ] Удалить 12 мёртвых методов Категории А:
  - `image_repository`: get_by_status, count_by_project, count_by_status
  - `task_repository`: get_pending_tasks, get_running_tasks
  - `annotation_service`: update_fields, has_annotation, get_all_annotations
  - `image_service`: image_exists, original_exists, get_original, is_image_used_in_other_projects
  - `project_service`: is_image_used_in_projects
- [ ] Запустить тесты для проверки что ничего не сломалось
- [ ] Проверить vulture снова после удаления
- [ ] Настроить pre-commit хук для vulture/ruff
- [ ] Исправить проблему с инициализацией AI моделей в тестах (таймаут)
- [ ] Исправить проблему с БД в тестах (пересоздают основную database.db)

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (исправлять СРОЧНО)

### 1. N+1 запросы к базе данных

**Статус:** ❌ Не исправлено
**Приоритет:** 🔴 КРИТИЧНО
**Время на фикс:** 1.5 часа
**Риск:** Высокий — деградация производительности при росте данных

**Проблема:**

В трёх сервисах запросы к БД выполняются в цикле:

```python
# services/project_service.py:135-148
def get_all_projects(self) -> List[Dict[str, Any]]:
    projects = project_repo.get_all()
    for project in projects:  # ← Цикл
        images = image_repo.get_by_project(project.id)  # ← ЗАПРОС НА КАЖДЫЙ
```

**Последствия:**
- `get_all_projects()` → 1 + N запросов (100 проектов = 101 запрос)
- `get_all_images()` → 1 + N запросов (1000 изображений = 1001 запрос)
- `get_all_annotations()` → 1 + N запросов

**Решение:**

```python
# Получить все изображения одним запросом
all_images = image_repo.get_all()
images_by_project = {}
for img in all_images:
    images_by_project.setdefault(img.project_id, []).append(img)

for project in projects:
    images = images_by_project.get(project.id, [])
```

**Файлы для изменения:**
- `services/project_service.py` (get_all_projects)
- `services/image_service.py` (get_all_images)
- `services/annotation_service.py` (get_all_annotations)

---

### 2. Нет rate limiting

**Статус:** ❌ Не исправлено
**Приоритет:** 🔴 КРИТИЧНО
**Время на фикс:** 30 минут
**Риск:** DDoS атаки, перегрузка GPU

**Проблема:**

```python
# Любой может делать 1000 запросов в секунду
@app.route('/api/detect_lines', methods=['POST'])
def detect_lines():
    # GPU будет загружен на 100%
```

**Решение:**

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(app, key_func=get_remote_address)

@app.route('/api/detect_lines', methods=['POST'])
@limiter.limit("5 per minute")
def detect_lines():
    ...
```

**Файлы для изменения:**
- `app.py` (добавить limiter)
- `pyproject.toml` (добавить flask-limiter)

---

### 3. Нет валидации входных данных

**Статус:** ❌ Не исправлено
**Приоритет:** 🔴 КРИТИЧНО
**Время на фикс:** 2 часа
**Риск:** Безопасность — XSS, path traversal, SQL injection

**Проблема:**

```python
@app.route('/api/save', methods=['POST'])
def save_data():
    incoming_data = request.json
    filename = incoming_data.get('image_name')  # ← Нет проверки!
    
    # regions может быть любым
    for key in ['regions', 'texts', 'status']:
        if key in incoming_data:
            existing_data[key] = incoming_data[key]  # ← Слепое копирование
```

**Атака:**
```json
{
  "image_name": "../../../etc/passwd",
  "regions": [{"points": "<script>alert('XSS')</script>"}],
  "status": "'; DROP TABLE images; --"
}
```

**Решение:**

```python
from marshmallow import Schema, fields, validate

class AnnotationSchema(Schema):
    image_name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    regions = fields.List(fields.Dict(), validate=validate.Length(max=500))
    status = fields.Str(validate=validate.OneOf(['crop', 'cropped', 'segment', 'texted']))

schema = AnnotationSchema()

@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        data = schema.load(request.json)  # ← Валидация
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
```

**Файлы для изменения:**
- `app.py` (добавить валидацию)
- `pyproject.toml` (добавить marshmallow)

---

### 4. SQLAlchemy сессии в цикле (нет транзакционности)

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

### 3. Нет валидации входных данных

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟡 СЕРЬЁЗНО  
**Время на фикс:** 3 часа  
**Риск:** Безопасность — инъекции, XSS, path traversal

**Проблема:**
```python
@app.route('/api/save', methods=['POST'])
def save_data():
    incoming_data = request.json
    filename = incoming_data.get('image_name')  # ← Нет проверки!
    
    # regions может быть любым
    for key in ['regions', 'texts', 'status']:
        if key in incoming_data:
            existing_data[key] = incoming_data[key]  # ← Слепое копирование
```

**Атака:**
```json
{
  "image_name": "../../../etc/passwd",
  "regions": "<script>alert('XSS')</script>",
  "status": "DROP TABLE images"
}
```

**Решение:**
```python
from marshmallow import Schema, fields, validate

class AnnotationSchema(Schema):
    image_name = fields.Str(required=True, validate=validate.Length(min=1, max=255))
    regions = fields.List(fields.Dict(), validate=validate.Length(max=500))
    texts = fields.Dict()
    status = fields.Str(validate=validate.OneOf(['crop', 'cropped', 'segment', 'texted']))

schema = AnnotationSchema()

@app.route('/api/save', methods=['POST'])
def save_data():
    try:
        data = schema.load(request.json)  # ← Валидация
    except ValidationError as e:
        return jsonify({'error': str(e)}), 400
```

**Файлы для изменения:**
- `app.py` (добавить валидацию)
- `pyproject.toml` (добавить marshmallow)
- `services/*.py` (валидация в сервисах)

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

### 7. Отсутствие индексов БД

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 15 минут
**Риск:** Медленные запросы к БД

**Проблема:**

```python
# database/models.py
class Image(Base):
    filename = Column(String(255), nullable=False)  # ← НЕТ ИНДЕКСА
```

**Последствие:** `get_by_filename()` выполняет полный скан таблицы

**Решение:**

```python
class Image(Base):
    filename = Column(String(255), nullable=False, index=True)
    
class Task(Base):
    __table_args__ = (
        Index('ix_tasks_status_created', 'status', 'created_at'),
    )
```

**Файлы для изменения:**
- `database/models.py`

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

### 8. Нет тестов на AI сервис

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟢 МЕЛКО  
**Время на фикс:** 4 часа

**Проблема:**
```python
# tests/ - нет тестов на ai_service.py
```

**Решение:** Добавить тесты на:
- detect_lines()
- recognize_text()
- recognize_text_in_region()

**Файлы для изменения:**
- `tests/test_ai_service.py` (создать)

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

- [ ] 1. Исправить сессии в batch операциях (транзакционность)

### В ЭТОЙ НЕДЕЛЕ 📅

- [ ] 2. Починить утечку памяти в `recognition_progress`
- [ ] 3. Добавить валидацию входных данных

### В СЛЕДУЮЩЕМ СПРИНТЕ 📆

- [ ] 4. Rate limiting
- [ ] 5. Автосохранение текста
- [ ] 6. Индикатор загрузки моделей

### ПО ЖЕЛАНИЮ 🕐

- [ ] 7. Убрать хардкод путей
- [ ] 8. Добавить тесты AI
- [ ] 9. Убрать magic numbers
- [ ] 10. Форматирование текста
- [ ] 11. Копирование изображения
- [ ] 12. Унификация фоновых задач
- [ ] 13. Ленивая инициализация TROCR
- [ ] 14. Исправление математики координат

---

## 📊 ИТОГОВАЯ ТАБЛИЦА

| # | Проблема | Приорит | Время | Статус |
|---|----------|---------|-------|--------|
| 1 | Сессии в цикле | 🔴 | 2 ч | ❌ |
| 2 | Утечка памяти | 🟡 | 1 ч | ❌ |
| 3 | Валидация input | 🟡 | 3 ч | ❌ |
| 4 | Rate limiting | 🟠 | 30 мин | ❌ |
| 5 | Автосохранение | 🟠 | 1 ч | ❌ |
| 6 | Индикатор загрузки | 🟠 | 2 ч | ❌ |
| 7 | Хардкод путей | 🟢 | 30 мин | ❌ |
| 8 | Тесты AI | 🟢 | 4 ч | ❌ |
| 9 | Magic numbers | 🟢 | 30 мин | ❌ |
| 10 | Форматирование текста | 🟠 | 2 ч | ❌ |
| 11 | Копирование изображения | 🟢 | 30 мин | ❌ |
| 12 | Унификация фоновых задач | 🟠 | 3 ч | ❌ |
| 13 | Ленивая инициализация TROCR | 🟡 | 1 ч | ❌ |
| 14 | Исправление математики координат | 🔴 | 4 ч | ❌ |

**Общее время на критические исправления:** ~6 часов
**Общее время на все исправления:** ~21 час

---

## 📝 ЗАМЕЧАНИЯ

### Зависимости для добавления

```toml
# pyproject.toml
[project]
dependencies = [
    "flask-limiter>=3.5.0",  # Rate limiting
    "marshmallow>=3.20.0",   # Валидация данных
    "flask-socketio>=5.3.0", # WebSocket для прогресса
]
```

### Тестирование после исправлений

1. **Batch операции:** Прервать на середине и проверить откат
2. **Память:** Создать 100+ задач и проверить утечки
3. **Валидация:** Попытаться отправить некорректные данные

---

## 🔗 ССЫЛКИ

- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/)
- [Marshmallow Documentation](https://marshmallow.readthedocs.io/)
- [SQLAlchemy Best Practices](https://docs.sqlalchemy.org/)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-19)

### 10. Форматирование текста

**Статус:** ❌ Не исправлено
**Приоритет:** 🟠 СРЕДНЕ
**Время на фикс:** 2 часа

**Описание:**
Добавить возможность форматирования текста в редакторе:
- **Сильное зачеркивание** — `[текст]` (квадратные скобки)
- **Слабое зачеркивание** — `~текст~` (тильды)

**Требования:**
- Кнопки в модальном окне ввода текста
- Обёртывание выделенного текста в формат
- Отображение в полигоне:
  - `[текст]` → жирный шрифт
  - `~текст~` → `text-decoration: line-through`
- Сохранение форматирования в БД (в поле `texts` как строки)

**Файлы для изменения:**
- `templates/text_editor.html` (toolbar с кнопками)
- `static/js/text_editor.js` (applyFormat, parseFormats)
- `static/css/style.css` (стили toolbar)

---

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
