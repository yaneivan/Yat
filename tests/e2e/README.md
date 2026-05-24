# E2E тесты на Playwright

End-to-End тесты для проверки работы приложения через браузер.

## Установка

Убедитесь, что установлены зависимости:

```bash
uv sync --group dev
```

Установите браузеры Playwright:

```bash
uv run playwright install chromium
```

## Запуск

### Базовый запуск (headless)

```bash
uv run pytest tests/e2e/
```

### С одним браузером

```bash
uv run pytest tests/e2e/test_auth.py -v
uv run pytest tests/e2e/test_projects.py -v
```

### Headed режим (с видимым браузером)

Headed режим включен в `.env` файле:

```bash
HEADED=true
uv run pytest tests/e2e/
```

Или через переменную окружения:

```bash
HEADED=true uv run pytest tests/e2e/
```

**Примечание:** Для headed режима нужен X сервер. На сервере/CI используйте xvfb:

```bash
HEADED=true xvfb-run uv run pytest tests/e2e/
```

Без X сервера будет ошибка "Missing X server".

## Конфигурация

Настройки в `tests/e2e/.env`:

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `USE_AUTOMATIC_SERVER` | Автозапуск сервера | `true` |
| `SERVER_URL` | URL сервера | `http://127.0.0.1:5000` |
| `ADMIN_USERNAME` | Логин админа | `admin` |
| `ADMIN_PASSWORD` | Пароль админа | `admin123` |
| `HEADED` | Видимый браузер | `false` |

## Тесты

### test_auth.py - Авторизация

| Тест | Описание |
|------|-----------|
| `test_login_page_loads` | Страница логина загружается |
| `test_successful_login` | Успешный вход -> редирект на главную |
| `test_failed_login_wrong_password` | Неверный пароль -> ошибка |
| `test_logout_redirects_to_login` | Выход -> редирект на /login |

### test_projects.py - Управление проектами

| Тест | Описание |
|------|-----------|
| `test_create_project_modal_opens` | Кнопка открывает модалку создания |
| `test_create_project_success` | Создание проекта -> карточка появляется |
| `test_delete_project` | Удаление проекта -> карточка исчезает |

## Требования

- Сервер должен быть доступен (или `USE_AUTOMATIC_SERVER=true`)
- В БД должна быть учетка admin/admin123
- Flask app должен отвечать на `SERVER_URL` (по умолчанию http://127.0.0.1:5000)