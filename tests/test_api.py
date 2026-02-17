"""
Минимальные тесты для Yat API.
Используем временную папку для данных — основная не засоряется.
"""
import pytest
import tempfile
import shutil
import os
from unittest.mock import patch

# Импортируем Flask приложение и storage
from app import app
import storage


@pytest.fixture
def temp_storage():
    """
    Фикстура создаёт временную папку для тестов.
    После теста — всё удаляется.
    """
    # Сохраняем оригинальные пути
    original_projects = storage.PROJECTS_FOLDER
    original_images = storage.IMAGE_FOLDER
    original_annotations = storage.ANNOTATION_FOLDER
    original_originals = storage.ORIGINALS_FOLDER
    
    # Создаём временную директорию
    tmpdir = tempfile.mkdtemp()
    
    # Подменяем пути на временные
    storage.PROJECTS_FOLDER = os.path.join(tmpdir, 'projects')
    storage.IMAGE_FOLDER = os.path.join(tmpdir, 'images')
    storage.ANNOTATION_FOLDER = os.path.join(tmpdir, 'annotations')
    storage.ORIGINALS_FOLDER = os.path.join(tmpdir, 'originals')
    
    # Создаём директории
    os.makedirs(storage.PROJECTS_FOLDER)
    os.makedirs(storage.IMAGE_FOLDER)
    os.makedirs(storage.ANNOTATION_FOLDER)
    os.makedirs(storage.ORIGINALS_FOLDER)
    
    yield tmpdir
    
    # Восстанавливаем оригинальные пути и удаляем временную папку
    storage.PROJECTS_FOLDER = original_projects
    storage.IMAGE_FOLDER = original_images
    storage.ANNOTATION_FOLDER = original_annotations
    storage.ORIGINALS_FOLDER = original_originals
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def client(temp_storage):
    """
    Фикстура создаёт тестовый клиент Flask.
    """
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_create_project(client):
    """
    Тест: создание проекта через POST /api/projects
    """
    response = client.post('/api/projects', 
                          json={'name': 'TestProject', 'description': 'Test desc'})
    data = response.get_json()
    
    assert response.status_code == 200
    assert data['status'] == 'success'
    assert data['project']['name'] == 'TestProject'


def test_get_projects_list(client):
    """
    Тест: получение списка проектов через GET /api/projects
    """
    # Сначала создадим проект
    client.post('/api/projects', json={'name': 'Project1', 'description': 'Desc1'})
    client.post('/api/projects', json={'name': 'Project2', 'description': 'Desc2'})
    
    # Получаем список
    response = client.get('/api/projects')
    data = response.get_json()
    
    assert response.status_code == 200
    assert len(data['projects']) == 2
    project_names = [p['name'] for p in data['projects']]
    assert 'Project1' in project_names
    assert 'Project2' in project_names


def test_create_project_empty_name(client):
    """
    Тест: создание проекта с пустым именем должно вернуть ошибку
    """
    response = client.post('/api/projects', 
                          json={'name': '', 'description': 'Test'})
    data = response.get_json()
    
    assert response.status_code == 400
    assert data['status'] == 'error'


def test_upload_image_to_project(client):
    """
    Тест: загрузка изображения в проект через POST /api/projects/<project>/upload_images
    """
    from io import BytesIO
    
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'ImageProject', 'description': 'Test'})
    
    # 2. Создаём тестовое изображение (1x1 пиксель, PNG)
    data = BytesIO()
    from PIL import Image
    img = Image.new('RGB', (1, 1), color='red')
    img.save(data, format='PNG')
    data.seek(0)
    
    # 3. Отправляем изображение
    response = client.post(
        '/api/projects/ImageProject/upload_images',
        data={'images': [(data, 'test_image.png')]},
        content_type='multipart/form-data'
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    assert 'Uploaded' in result['msg']
    
    # 4. Проверяем, что изображение появилось в проекте
    response = client.get('/api/projects/ImageProject/images')
    result = response.get_json()
    
    assert response.status_code == 200
    image_names = [img['name'] for img in result['images']]
    assert 'test_image.png' in image_names


def test_remove_image_from_project(client):
    """
    Тест: удаление изображения из проекта
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём изображение и проект
    data = BytesIO()
    img = Image.new('RGB', (1, 1), color='green')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post('/api/projects', json={'name': 'RemoveProj', 'description': ''})
    client.post(
        '/api/projects/RemoveProj/upload_images',
        data={'images': [(data, 'to_remove.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Проверяем, что изображение есть
    response = client.get('/api/projects/RemoveProj/images')
    result = response.get_json()
    image_names = [img['name'] for img in result['images']]
    assert 'to_remove.png' in image_names
    
    # 3. Удаляем изображение из проекта
    response = client.delete(
        '/api/projects/RemoveProj/images',
        json={'image_name': 'to_remove.png'}
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'

    # 4. Проверяем, что изображение удалено из проекта
    response = client.get('/api/projects/RemoveProj/images')
    result = response.get_json()
    image_names = [img['name'] for img in result['images']]
    assert 'to_remove.png' not in image_names


def test_load_nonexistent_annotation(client):
    """
    Тест: загрузка несуществующей аннотации возвращает дефолтное значение
    """
    response = client.get('/api/load/nonexistent.png')
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['regions'] == []
    assert result['texts'] == {}
    assert result['crop_params'] is None


def test_save_annotation_without_image_name(client):
    """
    Тест: сохранение без image_name возвращает ошибку
    """
    response = client.post('/api/save', json={'regions': []})
    result = response.get_json()

    assert response.status_code == 400
    assert result['status'] == 'error'
    assert 'filename' in result['msg'].lower()


def test_update_project(client):
    """
    Тест: редактирование проекта через PUT /api/projects/<name>
    """
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'UpdateProj', 'description': 'Old desc'})
    
    # 2. Редактируем
    response = client.put(
        '/api/projects/UpdateProj',
        json={'name': 'NewName', 'description': 'New desc'}
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    
    # 3. Проверяем, что проект обновился в списке
    response = client.get('/api/projects')
    result = response.get_json()
    project_names = [p['name'] for p in result['projects']]
    assert 'NewName' in project_names
    assert 'UpdateProj' not in project_names


def test_delete_project(client):
    """
    Тест: удаление проекта через DELETE /api/projects/<name>
    """
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'DeleteProj', 'description': ''})
    
    # 2. Проверяем, что проект есть
    response = client.get('/api/projects')
    result = response.get_json()
    project_names = [p['name'] for p in result['projects']]
    assert 'DeleteProj' in project_names
    
    # 3. Удаляем проект
    response = client.delete('/api/projects/DeleteProj')
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    
    # 4. Проверяем, что проект удалён
    response = client.get('/api/projects')
    result = response.get_json()
    project_names = [p['name'] for p in result['projects']]
    assert 'DeleteProj' not in project_names


def test_get_images_list(client):
    """
    Тест: получение списка всех изображений через GET /api/images_list
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект и загружаем изображение
    client.post('/api/projects', json={'name': 'ListProj', 'description': ''})
    
    data = BytesIO()
    img = Image.new('RGB', (1, 1), color='blue')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post(
        '/api/projects/ListProj/upload_images',
        data={'images': [(data, 'test_img.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Получаем список изображений
    response = client.get('/api/images_list')
    result = response.get_json()
    
    assert response.status_code == 200
    # Возвращается просто список имён файлов
    assert isinstance(result, list)
    assert 'test_img.png' in result


def test_get_tasks(client):
    """
    Тест: получение списка задач через GET /api/tasks
    """
    response = client.get('/api/tasks')
    result = response.get_json()

    assert response.status_code == 200
    assert 'tasks' in result
    assert isinstance(result['tasks'], list)


def test_get_task_by_id(client):
    """
    Тест: получение задачи по ID через GET /api/tasks/<task_id>
    """
    response = client.get('/api/tasks/nonexistent-task-id')
    # Задача не найдена — возвращает 404
    assert response.status_code == 404


def test_delete_image(client):
    """
    Тест: удаление изображения через POST /api/delete
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект и загружаем изображение
    client.post('/api/projects', json={'name': 'DeleteProj', 'description': ''})
    
    data = BytesIO()
    img = Image.new('RGB', (1, 1), color='yellow')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post(
        '/api/projects/DeleteProj/upload_images',
        data={'images': [(data, 'to_delete.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Проверяем, что изображение есть в images_list
    response = client.get('/api/images_list')
    result = response.get_json()
    assert 'to_delete.png' in result
    
    # 3. Удаляем изображение (передаём filenames массивом)
    response = client.post(
        '/api/delete',
        json={'filenames': ['to_delete.png']}
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    assert result['deleted'] == 1
    
    # 4. Проверяем, что изображение удалено
    response = client.get('/api/images_list')
    result = response.get_json()
    assert 'to_delete.png' not in result


def test_load_annotation_empty(client):
    """
    Тест: загрузка аннотации для файла без аннотации
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект и загружаем изображение (без аннотации)
    client.post('/api/projects', json={'name': 'LoadProj', 'description': ''})
    
    data = BytesIO()
    img = Image.new('RGB', (1, 1), color='cyan')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post(
        '/api/projects/LoadProj/upload_images',
        data={'images': [(data, 'no_annotation.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Загружаем аннотацию
    response = client.get('/api/load/no_annotation.png')
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['regions'] == []
    assert result['texts'] == {}


def test_crop_without_data(client):
    """
    Тест: crop без данных возвращает ошибку
    """
    response = client.post('/api/crop', json={})
    result = response.get_json()
    
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_detect_lines_without_image(client):
    """
    Тест: detect_lines без image_name возвращает ошибку
    """
    response = client.post('/api/detect_lines', json={})
    result = response.get_json()
    
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_recognize_text_without_image(client):
    """
    Тест: recognize_text без image_name возвращает ошибку
    """
    response = client.post('/api/recognize_text', json={})
    result = response.get_json()
    
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_recognize_progress_for_nonexistent_file(client):
    """
    Тест: прогресс распознавания для несуществующего файла
    """
    response = client.get('/api/recognize_progress/nonexistent.png')
    # Возвращает 200 с пустым прогрессом или ошибку
    assert response.status_code in [200, 400, 404]


def test_import_zip_without_file(client):
    """
    Тест: import_zip без файла возвращает ошибку
    """
    response = client.post('/api/import_zip')
    result = response.get_json()
    
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_batch_detect_for_empty_project(client):
    """
    Тест: batch_detect для пустого проекта возвращает ошибку
    """
    # 1. Создаём пустой проект
    client.post('/api/projects', json={'name': 'EmptyBatch', 'description': ''})
    
    # 2. Запускаем batch_detect
    response = client.post(
        '/api/projects/EmptyBatch/batch_detect',
        json={'settings': {}}
    )
    result = response.get_json()
    
    # Пустой проект — ошибка (нет изображений для обработки)
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_batch_recognize_for_empty_project(client):
    """
    Тест: batch_recognize для пустого проекта возвращает ошибку
    """
    # 1. Создаём пустой проект
    client.post('/api/projects', json={'name': 'EmptyRec', 'description': ''})
    
    # 2. Запускаем batch_recognize
    response = client.post(
        '/api/projects/EmptyRec/batch_recognize',
        json={'settings': {}}
    )
    result = response.get_json()
    
    # Пустой проект — ошибка (нет изображений для обработки)
    assert response.status_code == 400
    assert result['status'] == 'error'


def test_get_single_project(client):
    """
    Тест: получение одного проекта через GET /api/projects/<name>
    """
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'SingleProj', 'description': 'Test desc'})
    
    # 2. Получаем проект
    response = client.get('/api/projects/SingleProj')
    result = response.get_json()
    
    assert response.status_code == 200
    assert 'project' in result
    assert result['project']['name'] == 'SingleProj'
    assert result['project']['description'] == 'Test desc'


def test_serve_image(client):
    """
    Тест: отдача изображения через GET /data/images/<filename>
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Загружаем изображение
    client.post('/api/projects', json={'name': 'ServeProj', 'description': ''})
    
    data = BytesIO()
    img = Image.new('RGB', (10, 10), color='red')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post(
        '/api/projects/ServeProj/upload_images',
        data={'images': [(data, 'serve_test.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Получаем изображение
    response = client.get('/data/images/serve_test.png')
    
    assert response.status_code == 200
    assert response.content_type == 'image/png'


def test_home_page(client):
    """
    Тест: главная страница возвращает 200
    """
    response = client.get('/')
    assert response.status_code == 200


def test_project_page(client):
    """
    Тест: страница проекта возвращает 200
    """
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'PageProj', 'description': ''})
    
    # 2. Получаем страницу проекта
    response = client.get('/project/PageProj')
    assert response.status_code == 200


def test_serve_original_image(client):
    """
    Тест: отдача оригинала изображения через GET /data/originals/<filename>
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект и загружаем изображение (оно копируется в originals)
    client.post('/api/projects', json={'name': 'OriginalProj', 'description': ''})
    
    data = BytesIO()
    img = Image.new('RGB', (10, 10), color='green')
    img.save(data, format='PNG')
    data.seek(0)
    
    client.post(
        '/api/projects/OriginalProj/upload_images',
        data={'images': [(data, 'original_test.png')]},
        content_type='multipart/form-data'
    )
    
    # 2. Получаем оригинал изображения
    response = client.get('/data/originals/original_test.png')
    
    assert response.status_code == 200
    assert response.content_type == 'image/png'


def test_editor_page(client):
    """
    Тест: страница редактора сегментов возвращает 200
    """
    # Требуется параметр image
    response = client.get('/editor?image=test.png')
    assert response.status_code == 200


def test_text_editor_page(client):
    """
    Тест: страница текстового редактора возвращает 200
    """
    # Требуется параметр image
    response = client.get('/text_editor?image=test.png')
    assert response.status_code == 200


def test_cropper_page(client):
    """
    Тест: страница кроппера возвращает 200
    """
    # Требуется параметр image
    response = client.get('/cropper?image=test.png')
    assert response.status_code == 200


def test_export_project_zip(client):
    """
    Тест: экспорт проекта через GET /api/projects/<name>/export_zip
    """
    from io import BytesIO
    from PIL import Image
    import zipfile

    # 1. Создаём проект с изображением
    client.post('/api/projects', json={'name': 'ExportProj', 'description': ''})

    data = BytesIO()
    img = Image.new('RGB', (10, 10), color='blue')
    img.save(data, format='PNG')
    data.seek(0)

    response = client.post(
        '/api/projects/ExportProj/upload_images',
        data={'images': [(data, 'export_test.png')]},
        content_type='multipart/form-data'
    )

    # 1.5. Сохраняем аннотацию с текстом (используем правильный endpoint /api/save)
    # Frontend stores texts with keys '0', '1', '2' (not 'l0', 'l1', 'l2')
    client.post('/api/save', json={
        'image_name': 'export_test.png',
        'regions': [{'points': [{'x': 1, 'y': 1}, {'x': 5, 'y': 1}, {'x': 5, 'y': 5}, {'x': 1, 'y': 5}]}],
        'texts': {'0': 'Тестовый текст'}
    })

    # 2. Экспортируем проект
    response = client.get('/api/projects/ExportProj/export_zip')

    # Должен вернуть ZIP файл
    assert response.status_code == 200

    # 3. Проверяем содержимое ZIP
    with zipfile.ZipFile(BytesIO(response.data)) as zf:
        # Проверяем, что XML содержит текст
        xml_content = zf.read('export_test.xml').decode('utf-8')
        assert '<Unicode>Тестовый текст</Unicode>' in xml_content
    assert 'zip' in response.content_type.lower() or response.content_type == 'application/zip'


def test_crop_image(client):
    """
    Тест: обрезка изображения через POST /api/crop
    """
    from io import BytesIO
    from PIL import Image
    import time
    import os
    from storage import ORIGINALS_FOLDER, IMAGE_FOLDER, ANNOTATION_FOLDER

    # 1. Создаём проект с изображением
    client.post('/api/projects', json={'name': 'CropProj', 'description': ''})

    data = BytesIO()
    img = Image.new('RGB', (100, 100), color='red')
    img.save(data, format='PNG')
    data.seek(0)

    client.post(
        '/api/projects/CropProj/upload_images',
        data={'images': [(data, 'crop_test.png')]},
        content_type='multipart/form-data'
    )

    # 2. Проверяем, что изображение есть в originals и images
    print(f"Originals folder: {ORIGINALS_FOLDER}")
    print(f"Images folder: {IMAGE_FOLDER}")
    print(f"Original exists: {os.path.exists(os.path.join(ORIGINALS_FOLDER, 'crop_test.png'))}")
    print(f"Image exists: {os.path.exists(os.path.join(IMAGE_FOLDER, 'crop_test.png'))}")

    # 3. Отправляем запрос на обрезку (формат с corners)
    response = client.post(
        '/api/crop',
        json={
            'image_name': 'crop_test.png',
            'box': {
                'corners': [
                    {'x': 10, 'y': 10},  # top-left
                    {'x': 10, 'y': 60},  # bottom-left
                    {'x': 60, 'y': 60},  # bottom-right
                    {'x': 60, 'y': 10}   # top-right
                ]
            }
        }
    )
    result = response.get_json()

    assert response.status_code == 200
    assert result['status'] == 'success'

    # 4. Ждём завершения фоновой обработки (5 секунд)
    time.sleep(5)

    # 5. Проверяем аннотацию
    response = client.get('/api/load/crop_test.png')
    result = response.get_json()

    print(f"Annotation folder: {ANNOTATION_FOLDER}")
    print(f"Annotation file exists: {os.path.exists(os.path.join(ANNOTATION_FOLDER, 'crop_test.png.json'))}")
    print(f"Load result: {result}")

    assert response.status_code == 200
    assert result['crop_params'] is not None
    assert len(result['crop_params']['corners']) == 4


def test_export_and_import_zip(client):
    """
    Тест: экспорт проекта в ZIP и импорт обратно
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'ExportTest', 'description': 'Test export'})
    
    # 2. Создаём тестовое изображение
    img_data = BytesIO()
    img = Image.new('RGB', (100, 100), color='red')
    img.save(img_data, format='PNG')
    img_data.seek(0)
    
    # 3. Загружаем изображение
    response = client.post(
        '/api/projects/ExportTest/upload_images',
        data={'images': [(img_data, 'test_export.png')]},
        content_type='multipart/form-data'
    )
    assert response.status_code == 200
    
    # 4. Сохраняем аннотацию
    client.post('/api/save', json={
        'image_name': 'test_export.png',
        'regions': [{'points': [{'x': 10, 'y': 10}, {'x': 50, 'y': 50}]}]
    })
    
    # 5. Экспортируем проект
    response = client.get('/api/projects/ExportTest/export_zip')
    assert response.status_code == 200
    assert response.mimetype == 'application/zip'
    
    # 6. Импортируем ZIP обратно (на главной странице - без project_name)
    response = client.post(
        '/api/import_zip',
        data={
            'file': (BytesIO(response.data), 'ExportTest.zip'),
            'simplify': '5'
        },
        content_type='multipart/form-data'
    )
    result = response.get_json()
    
    # Импорт создаст новый проект с похожим именем
    assert response.status_code == 200
    assert result['status'] == 'success'
    assert result['count'] >= 1


def test_import_zip_to_project(client):
    """
    Тест: импорт ZIP в существующий проект (со страницы проекта)
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект
    client.post('/api/projects', json={'name': 'ImportTarget', 'description': 'Target for import'})
    
    # 2. Создаём другой проект для экспорта
    client.post('/api/projects', json={'name': 'ExportSource', 'description': 'Source for export'})
    
    # 3. Загружаем изображение в проект-источник
    img_data = BytesIO()
    img = Image.new('RGB', (100, 100), color='blue')
    img.save(img_data, format='PNG')
    img_data.seek(0)
    
    client.post(
        '/api/projects/ExportSource/upload_images',
        data={'images': [(img_data, 'test_import.png')]},
        content_type='multipart/form-data'
    )
    
    # 4. Экспортируем проект-источник
    response = client.get('/api/projects/ExportSource/export_zip')
    assert response.status_code == 200
    
    # 5. Импортируем ZIP в проект-цель (со страницы проекта)
    response = client.post(
        '/api/import_zip',
        data={
            'file': (BytesIO(response.data), 'ExportSource.zip'),
            'simplify': '5',
            'project_name': 'ImportTarget'
        },
        content_type='multipart/form-data'
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    assert result['count'] >= 1
    assert result['project_name'] == 'ImportTarget'

    # 6. Проверяем, что изображение добавлено в проект
    response = client.get('/api/projects/ImportTarget/images')
    result = response.get_json()

    assert response.status_code == 200
    assert len(result) >= 1


def test_import_zip_to_project_with_cyrillic_name(client):
    """
    Тест: импорт ZIP в проект с кириллическим именем (со страницы проекта)
    Проверяет корректную работу с URL-кодированием
    """
    from io import BytesIO
    from PIL import Image
    
    # 1. Создаём проект с кириллическим именем
    client.post('/api/projects', json={'name': 'Тест', 'description': 'Тестовый проект'})
    
    # 2. Создаём другой проект для экспорта
    client.post('/api/projects', json={'name': 'ExportSource2', 'description': 'Source for export'})
    
    # 3. Загружаем изображение в проект-источник
    img_data = BytesIO()
    img = Image.new('RGB', (100, 100), color='green')
    img.save(img_data, format='PNG')
    img_data.seek(0)
    
    client.post(
        '/api/projects/ExportSource2/upload_images',
        data={'images': [(img_data, 'test_cyrillic.png')]},
        content_type='multipart/form-data'
    )
    
    # 4. Экспортируем проект-источник
    response = client.get('/api/projects/ExportSource2/export_zip')
    assert response.status_code == 200
    
    # 5. Импортируем ZIP в проект с кириллическим именем
    # Эмулируем поведение фронтенда с decodeURIComponent
    response = client.post(
        '/api/import_zip',
        data={
            'file': (BytesIO(response.data), 'ExportSource2.zip'),
            'simplify': '5',
            'project_name': 'Тест'  # Фронтенд отправляет декодированное имя
        },
        content_type='multipart/form-data'
    )
    result = response.get_json()
    
    assert response.status_code == 200
    assert result['status'] == 'success'
    assert result['count'] >= 1
    assert result['project_name'] == 'Тест'
    
    # 6. Проверяем, что изображение добавлено в проект
    response = client.get('/api/projects/Тест/images')
    result = response.get_json()
    
    assert response.status_code == 200
    assert len(result) >= 1
