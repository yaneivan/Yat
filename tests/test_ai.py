"""
Тесты для AI сервиса (AIService).

Эти тесты требуют реальные AI модели и работают медленно.
Запускать отдельно: pytest tests/test_ai.py -v

Быстрые тесты API — в test_api.py (AI замокан).
"""
import pytest
import threading
import time
from unittest.mock import patch, MagicMock

# Импортируем AI сервис напрямую (без Flask app)
from services.ai_service import AIService


@pytest.fixture
def fresh_ai_service():
    """
    Фикстура создаёт НОВЫЙ AIService для каждого теста.
    """
    service = AIService()
    yield service
    # Очистка
    service._yolo_model = None
    service._trocr_model = None
    service._trocr_processor = None


class TestAIService:
    """Тесты для AIService."""

    def test_ai_service_initialization(self, fresh_ai_service):
        """Тест: AI сервис создаётся с пустыми моделями."""
        assert fresh_ai_service._yolo_model is None
        assert fresh_ai_service._trocr_model is None
        assert fresh_ai_service._trocr_processor is None

    def test_is_yolo_available(self, fresh_ai_service):
        """Тест: проверка доступности YOLO."""
        try:
            result = fresh_ai_service.is_yolo_available()
            assert isinstance(result, bool)
        except FileNotFoundError as e:
            # Модель YOLO не найдена — это не баг кода
            pytest.skip(f"YOLO model not found: {e}")
        except Exception as e:
            # GPU может быть недоступен или несовместим
            # Это не баг кода, а аппаратное ограничение
            if "CUDA" in str(e) or "GPU" in str(e):
                pytest.skip(f"GPU not available: {e}")
            else:
                raise

    def test_is_trocr_available(self, fresh_ai_service):
        """Тест: проверка доступности TROCR."""
        result = fresh_ai_service.is_trocr_available()
        assert isinstance(result, bool)

    # =============================================================================
    # 🔴 КРИТИЧНЫЙ ТЕСТ: Race condition при инициализации
    # =============================================================================

    def test_concurrent_trocr_initialization(self, fresh_ai_service):
        """
        Тест: одновременная инициализация TROCR из нескольких потоков.

        🔧 Теперь это работает — блокировка предотвращает гонку

        Проверяем что только ОДИН поток выполняет инициализацию,
        даже если 5 потоков одновременно вызовут _get_trocr_model()
        """
        if not fresh_ai_service.is_trocr_available():
            pytest.skip("TROCR not available, skipping race condition test")

        init_count = [0]  # Счётчик инициализаций
        init_lock = threading.Lock()
        barrier = threading.Barrier(5)  # Синхронизация потоков

        def counting_init(*args, **kwargs):
            with init_lock:
                init_count[0] += 1
                # Установить модели после первой инициализации
                if init_count[0] == 1:
                    fresh_ai_service._trocr_model = MagicMock()
                    fresh_ai_service._trocr_processor = MagicMock()
            # Имитация задержки инициализации
            time.sleep(0.1)
            return fresh_ai_service._trocr_model, fresh_ai_service._trocr_processor

        # Подменить метод инициализации
        with patch.object(fresh_ai_service, '_initialize_trocr', side_effect=counting_init):
            # Инициализировать один раз для mock
            fresh_ai_service._trocr_model = None
            fresh_ai_service._trocr_processor = None

            errors = []

            def worker():
                try:
                    barrier.wait()  # Ждать пока все потоки будут готовы
                    fresh_ai_service._get_trocr_model()
                except Exception as e:
                    errors.append(e)

            # Запустить 5 потоков одновременно
            threads = []
            for _ in range(5):
                t = threading.Thread(target=worker)
                threads.append(t)
                t.start()

            # Подождать завершение
            for t in threads:
                t.join(timeout=10)

            # Проверить что ошибок не было
            assert len(errors) == 0, f"Errors during concurrent init: {errors}"

            # ✅ ПРОВЕРКА: инициализация должна вызваться только 1 раз
            # Благодаря блокировке только один поток выполнит инициализацию
            assert init_count[0] == 1, (
                f"Race condition detected! _initialize_trocr called {init_count[0]} times "
                f"instead of 1. Multiple threads initialized TROCR simultaneously."
            )

    def test_get_trocr_model_returns_pair(self, fresh_ai_service):
        """Тест: _get_trocr_model возвращает кортеж (model, processor)."""
        if not fresh_ai_service.is_trocr_available():
            pytest.skip("TROCR not available")

        # Пропустить реальную загрузку
        with patch.object(fresh_ai_service, '_initialize_trocr'):
            fresh_ai_service._trocr_model = MagicMock()
            fresh_ai_service._trocr_processor = MagicMock()

            model, processor = fresh_ai_service._get_trocr_model()

            assert model is not None
            assert processor is not None

    def test_detect_lines_mocked(self, fresh_ai_service):
        """
        Тест: обнаружение линий с моком.

        Проверяет что метод вызывается корректно.
        """
        # Mock YOLO_AVAILABLE flag и _get_yolo_model
        with patch('services.ai_service.YOLO_AVAILABLE', False):
            # Должен выбросить исключение что YOLO недоступен
            with pytest.raises(Exception, match="YOLOv9 not available"):
                fresh_ai_service.detect_lines("test.png")

    def test_recognize_text_mocked(self, fresh_ai_service):
        """
        Тест: распознавание текста с моком.

        Проверяет что метод вызывается корректно.
        """
        # Mock TROCR_AVAILABLE flag
        with patch('services.ai_service.TROCR_AVAILABLE', False):
            # Должен выбросить исключение что TROCR недоступен
            with pytest.raises(Exception, match="Transformers not available"):
                fresh_ai_service.recognize_text("test.png", [])
