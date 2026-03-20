# TODO: Критические проблемы и план исправлений

**Дата создания:** 2026-03-16
**Приоритет:** Критические проблемы безопасности и стабильности

---

## ✅ РЕАЛИЗОВАННЫЕ ФУНКЦИИ (2026-03-19)

### Система разделения прав пользователей

**Статус:** ✅ Реализовано
**Дата:** 2026-03-19

**Описание:**
- Двухуровневая система: Admin и User
- Пароли задаются в `.env` файле
- Admin — полный доступ, User — только чтение и разметка

**Конфигурация:**
```bash
# .env
ADMIN_PASSWORD=admin123      # Полный доступ
USER_PASSWORD=user123        # Только чтение (опционально)
```

**Логика:**
- Нет паролей → все admin (открытый доступ)
- Только ADMIN_PASSWORD → все admin
- Оба пароля → admin и user роли
- Только USER_PASSWORD → ошибка при старте

**Защищённые endpoint'ы (только admin):**
- `POST /api/projects` — создать проект
- `PUT /api/projects/<name>` — редактировать проект
- `DELETE /api/projects/<name>` — удалить проект
- `POST /api/projects/<name>/upload_images` — загрузить изображения
- `DELETE /api/projects/<name>/images` — удалить изображение
- `POST /api/import_zip` — импорт ZIP
- `POST /api/projects/<name>/batch_detect` — batch детекция
- `POST /api/projects/<name>/batch_recognize` — batch распознавание

**UI изменения:**
- Отображение роли в шапке (👤 Admin / 👤 User)
- Скрытие кнопок для user (создание, удаление, импорт, загрузка, batch)
- Logout кнопка работает корректно

**Файлы:**
- `.env` (новый)
- `config.py` (чтение паролей)
- `app.py` (логика входа, middleware, защита endpoint'ов)
- `templates/index.html` (роль в шапке, скрытие кнопок)
- `templates/project.html` (скрытие кнопок)

---

## 🔴 КРИТИЧЕСКИЕ ПРОБЛЕМЫ (исправлять СРОЧНО)

### 1. Отсутствие CSRF защиты

**Статус:** ❌ Не исправлено  
**Приоритет:** 🔴 КРИТИЧНО  
**Время на фикс:** 5 минут  
**Риск:** Высокий — XSS атаки, подделка запросов

**Проблема:**
```python
# app.py - нет CSRF токенов
@app.route('/api/save', methods=['POST'])
def save_data():
    # Любой сайт может сделать POST запрос и испортить данные
```

**Решение:**
```python
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'change-this')
csrf = CSRFProtect(app)  # ← Включить CSRF
```

**Файлы для изменения:**
- `app.py`
- `pyproject.toml` (добавить flask-wtf)
- `templates/*.html` (добавить {{ csrf_token() }} в формы)

---

### 2. SQLAlchemy сессии в цикле (нет транзакционности)

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

### 3. DEBUG PRINT в продакшене

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟡 СЕРЬЁЗНО  
**Время на фикс:** 1 час  
**Риск:** Замедление, утечка информации, отсутствие ротации логов

**Проблема:**
```python
# app.py - 78 print() вызовов в коде
print(f"[DEBUG] Saving annotation for {validated}: {len(regions)} regions")
print(f"[DEBUG] Save successful")
print(f"[DEBUG] ValueError: {e}")
```

**Решение:**
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

logger.info(f"Saving annotation for {filename}")
logger.error(f"Database error: {e}", exc_info=True)
```

**Файлы для изменения:**
- `app.py`
- `logic.py`
- `services/*.py`
- `storage.py`

---

### 4. Нет обработки "database is locked"

**Статус:** ❌ Не исправлено  
**Приоритет:** 🟡 СЕРЬЁЗНО  
**Время на фикс:** 30 минут  
**Риск:** Блокировки БД при одновременной записи

**Проблема:**
```python
# database/session.py
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}  # ← Нет timeout!
)
```

**Сценарий:**
1. Batch распознавание (50 файлов, 5 минут)
2. Пользователь сохраняет аннотацию
3. **OperationalError: database is locked**
4. Данные потеряны

**Решение:**
```python
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "check_same_thread": False,
        "timeout": 60  # ← Ждать 60 секунд
    }
)

# Включить WAL mode
def init_db():
    from database import models
    Base.metadata.create_all(bind=engine)
    
    # Включить WAL для лучшей конкурентности
    conn = engine.connect()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
```

**Файлы для изменения:**
- `database/session.py`

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

### 6. Нет валидации входных данных

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

### 7. Нет rate limiting

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

### 9. Нет индикатора загрузки модели

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

### 10. Хардкод путей

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

### 11. Нет тестов на AI сервис

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

### 12. Magic numbers

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

### СРОЧНО (сегодня) ✅

- [ ] 1. Включить CSRF защиту
- [ ] 2. Добавить `timeout=60` в SQLite
- [ ] 3. Убрать DEBUG PRINT или заменить на logging

### В ЭТОЙ НЕДЕЛЕ 📅

- [ ] 4. Исправить сессии в batch операциях (транзакционность)
- [ ] 5. Починить утечку памяти в `recognition_progress`
- [ ] 6. Добавить валидацию входных данных

### В СЛЕДУЮЩЕМ СПРИНТЕ 📆

- [ ] 7. Rate limiting
- [ ] 8. Автосохранение текста
- [ ] 9. Индикатор загрузки моделей

### ПО ЖЕЛАНИЮ 🕐

- [ ] 10. Убрать хардкод путей
- [ ] 11. Добавить тесты AI
- [ ] 12. Убрать magic numbers

---

## 📊 ИТОГОВАЯ ТАБЛИЦА

| # | Проблема | Приорит | Время | Статус |
|---|----------|---------|-------|--------|
| 1 | CSRF защита | 🔴 | 5 мин | ❌ |
| 2 | Сессии в цикле | 🔴 | 2 ч | ❌ |
| 3 | DEBUG PRINT | 🟡 | 1 ч | ❌ |
| 4 | SQLite timeout | 🟡 | 30 мин | ❌ |
| 5 | Утечка памяти | 🟡 | 1 ч | ❌ |
| 6 | Валидация input | 🟡 | 3 ч | ❌ |
| 7 | Rate limiting | 🟠 | 30 мин | ❌ |
| 8 | Автосохранение | 🟠 | 1 ч | ❌ |
| 9 | Индикатор загрузки | 🟠 | 2 ч | ❌ |
| 10 | Хардкод путей | 🟢 | 30 мин | ❌ |
| 11 | Тесты AI | 🟢 | 4 ч | ❌ |
| 12 | Magic numbers | 🟢 | 30 мин | ❌ |
| 13 | Форматирование текста | 🟠 | 2 ч | ❌ |
| 14 | Копирование изображения | 🟢 | 30 мин | ❌ |

**Общее время на критические исправления:** ~8 часов
**Общее время на все исправления:** ~20 часов

---

## 📝 ЗАМЕЧАНИЯ

### Зависимости для добавления

```toml
# pyproject.toml
[project]
dependencies = [
    "flask-wtf>=1.2.0",      # CSRF защита
    "flask-limiter>=3.5.0",  # Rate limiting
    "marshmallow>=3.20.0",   # Валидация данных
    "flask-socketio>=5.3.0", # WebSocket для прогресса
]
```

### Тестирование после исправлений

1. **CSRF:** Проверить что формы отправляются с токеном
2. **Batch операции:** Прервать на середине и проверить откат
3. **SQLite:** Запустить две batch операции параллельно
4. **Память:** Создать 100+ задач и проверить утечки
5. **Валидация:** Попытаться отправить некорректные данные

---

## 🔗 ССЫЛКИ

- [Flask-WTF Documentation](https://flask-wtf.readthedocs.io/)
- [Flask-Limiter Documentation](https://flask-limiter.readthedocs.io/)
- [Marshmallow Documentation](https://marshmallow.readthedocs.io/)
- [SQLAlchemy Best Practices](https://docs.sqlalchemy.org/)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)

---

## 📋 НОВЫЕ ЗАДАЧИ (добавлено 2026-03-19)

### 13. Форматирование текста

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

### 14. Копирование изображения региона

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
