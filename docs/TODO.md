# TODO: Критические проблемы и план исправлений

**Приоритет:** Критические проблемы безопасности и стабильности

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (исправлять СРОЧНО)

### 1. SQLAlchemy сессии в цикле (нет транзакционности)

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

### 2. Утечка памяти в recognition_progress

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

### 4. Нет rate limiting

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟠 СРЕДНЕ  
**Время на фикс:** 30 минут  
**Риск:** DDoS, перегрузка GPU

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
@limiter.limit("10 per minute")
def detect_lines():
    ...
```

**Файлы для изменения:**
- `app.py`
- `pyproject.toml` (добавить flask-limiter)

---

### 5. Текст в модалках не автосохраняется

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
