# 🔐 CSRF Защита в Yat

**Дата добавления:** 2026-03-20  
**Статус:** ✅ Реализовано

---

## Что такое CSRF?

**CSRF (Cross-Site Request Forgery)** — это тип атаки, при котором злоумышленник заставляет браузер жертвы выполнить нежелательные действия на доверенном сайте.

### Сценарий атаки (без CSRF защиты):

1. Пользователь заходит на `yat.com` и логинится как admin
2. Сессия активна (куки с `session_id` сохранены в браузере)
3. Пользователь переходит на `evil.com`
4. На `evil.com` есть скрытая форма:

```html
<!-- evil.com -->
<form action="https://yat.com/api/projects/important-project/delete" method="POST">
  <input type="submit" value="Нажми чтобы получить приз!">
</form>
```

5. Пользователь нажимает кнопку → браузер отправляет **POST запрос с куками сессии**
6. **Проект удалён** от имени пользователя

**Проблема:** Браузер автоматически отправляет куки на тот же домен, даже если запрос инициирован с другого сайта.

---

## Как работает CSRF защита в Yat?

### Механизм защиты:

1. **Сервер генерирует случайный токен** при загрузке страницы
2. **Токен сохраняется в сессии** и в форме (скрытое поле)
3. **При отправке формы сервер проверяет:** совпадает ли токен в форме с токеном в сессии
4. **`evil.com` не может узнать токен** → не может подделать запрос

### Реализация:

```python
# app.py
from flask_wtf.csrf import CSRFProtect

app = Flask(__name__)
app.config['WTF_CSRF_ENABLED'] = True
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Токен не истекает
csrf = CSRFProtect(app)
```

```html
<!-- templates/login.html -->
<form method="POST">
    <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
    <input type="password" name="password" placeholder="Пароль">
    <button type="submit">Войти</button>
</form>
```

```javascript
// static/js/api.js (для AJAX запросов)
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

fetch('/api/projects/test', {
    method: 'DELETE',
    headers: {
        'X-CSRFToken': csrfToken,
        'Content-Type': 'application/json'
    }
});
```

---

## Что защищено?

### ✅ Защищённые endpoint'ы:

**HTML формы:**
- `/login` — форма входа (csrf_token в скрытом поле)

**API endpoint'ы (все POST/PUT/DELETE запросы):**
- `POST /api/projects` — создать проект
- `PUT /api/projects/<name>` — редактировать проект
- `DELETE /api/projects/<name>` — удалить проект
- `POST /api/projects/<name>/upload_images` — загрузить изображения
- `DELETE /api/projects/<name>/images` — удалить изображение
- `POST /api/save` — сохранить аннотацию
- `POST /api/import_zip` — импорт ZIP
- `POST /api/projects/<name>/batch_detect` — batch детекция
- `POST /api/projects/<name>/batch_recognize` — batch распознавание

**Механизм защиты API:**
- CSRF токен в meta tag каждого шаблона
- JS функция `getCsrfHeaders()` добавляет токен ко всем POST/PUT/DELETE запросам
- Заголовок `X-CSRFToken` проверяется сервером

---

## Зависимости

```toml
# pyproject.toml
[project]
dependencies = [
    "flask-wtf>=1.2.0",  # CSRF защита
    "wtforms>=3.2.0",
]
```

---

## Тестирование

### Проверка что CSRF работает:

```bash
# POST без CSRF токена → 400 Bad Request
curl -X POST https://yat.com/login \
  -d "password=test"

# POST с CSRF токеном → 200 OK
curl -X POST https://yat.com/login \
  -d "password=admin123&csrf_token=abc123..."
```

### В браузере:

1. Открыть DevTools → Network
2. Отправить форму login
3. Проверить что в запросе есть `csrf_token`
4. Попробовать отправить без токена → получить 400

---

## Почему это важно для Yat?

### Риски без CSRF защиты:

| Атака | Последствие |
|-------|-------------|
| Удаление проекта | Потеря данных аннотаций |
| Загрузка изображений | Порча данных, вредоносные файлы |
| Запуск batch операций | Перегрузка GPU, простой системы |
| Изменение аннотаций | Порча разметки данных |

### Кто в группе риска:

- **Публичный доступ** — если приложение доступно из интернета
- **Локальная сеть** — если несколько пользователей в одной сети
- **Общий компьютер** — если несколько пользователей за одним ПК

---

## Дополнительные меры безопасности

### 1. Role-based Access Control (RBAC)

Разделение на admin/user уже реализовано:
- Admin — полный доступ
- User — только чтение и разметка

### 2. Session Security

```python
# app.py
app.secret_key = os.environ.get('SECRET_KEY')  # Надёжный ключ
app.config['WTF_CSRF_TIME_LIMIT'] = None  # Токен не истекает
```

### 3. HTTPS (в production)

```bash
# Для Docker
# Используйте reverse proxy (nginx, traefik) с SSL
```

### 4. Rate Limiting (планируется)

Ограничение количества запросов в минуту для предотвращения DDoS.

---

## См. также

- [Flask-WTF Documentation](https://flask-wtf.readthedocs.io/)
- [OWASP CSRF Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)
- [TODO.md](TODO.md) — план исправления других проблем безопасности

---

## Чек-лист безопасности

- [x] CSRF защита включена
- [x] Токены в формах
- [x] Session-based auth для API
- [x] Role-based access control
- [ ] Rate limiting
- [ ] HTTPS в production
- [ ] Валидация входных данных
- [ ] Логирование вместо print()
