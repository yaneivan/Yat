"""
Image Storage Service — единый сервис для управления файлами изображений.

Отвечает за:
- Project-specific пути к файлам
- Создание директорий для проектов
- Проверку существования файлов
- Копирование/перемещение файлов
- Отдачу URL для фронтенда

Архитектура хранения:
  data/
  ├── images/
  │   ├── ProjectA/
  │   │   └── scan001.jpg
  │   ├── ProjectB/
  │   │   └── scan001.jpg
  │   └── (root files без проекта)
  └── originals/
      ├── ProjectA/
      │   └── scan001.jpg
      ├── ProjectB/
      │   └── scan001.jpg
      └── (root files без проекта)
"""

import os
import shutil

from storage import IMAGE_FOLDER, ORIGINALS_FOLDER, THUMBNAILS_FOLDER, ALLOWED_EXTENSIONS


class ImageStorageService:
    """
    Единый сервис для управления файлами изображений.
    
    Все файловые операции идут ТОЛЬКО через этот сервис.
    """

    def __init__(self):
        pass

    def _validate_filename(self, filename: str) -> str:
        """Validate filename for security."""
        if not filename:
            raise ValueError("Filename cannot be empty")
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError("Invalid filename: path traversal detected")
        return filename

    # --- Пути к файлам ---

    def get_image_folder(self, project_name: str = None) -> str:
        """Get images folder path, optionally project-specific."""
        if project_name:
            folder = os.path.join(IMAGE_FOLDER, project_name)
            os.makedirs(folder, exist_ok=True)
            return folder
        return IMAGE_FOLDER

    def get_original_folder(self, project_name: str = None) -> str:
        """Get originals folder path, optionally project-specific."""
        if project_name:
            folder = os.path.join(ORIGINALS_FOLDER, project_name)
            os.makedirs(folder, exist_ok=True)
            return folder
        return ORIGINALS_FOLDER

    def get_image_path(self, filename: str, project_name: str = None) -> str:
        """Get full path to image file, optionally project-specific."""
        validated = self._validate_filename(filename)
        folder = self.get_image_folder(project_name)
        return os.path.join(folder, validated)

    def get_original_path(self, filename: str, project_name: str = None) -> str:
        """Get full path to original file, optionally project-specific."""
        validated = self._validate_filename(filename)
        folder = self.get_original_folder(project_name)
        return os.path.join(folder, validated)

    # --- Проверки существования ---

    def image_exists(self, filename: str, project_name: str = None) -> bool:
        """Check if image exists."""
        try:
            path = self.get_image_path(filename, project_name)
            return os.path.exists(path)
        except ValueError:
            return False

    def original_exists(self, filename: str, project_name: str = None) -> bool:
        """Check if original backup exists."""
        try:
            path = self.get_original_path(filename, project_name)
            return os.path.exists(path)
        except ValueError:
            return False

    def ensure_original_exists(self, filename: str, project_name: str = None) -> bool:
        """
        Ensure original backup exists, copy from images if needed.
        
        Returns:
            True if original exists or was copied, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
        except ValueError:
            return False

        src = self.get_image_path(validated, project_name)
        dst = self.get_original_path(validated, project_name)

        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copy(src, dst)

        return os.path.exists(dst)

    # --- Загрузка изображений (PIL) ---

    def load_image(self, filename: str, project_name: str = None):
        """
        Load image from images folder.
        
        Returns:
            PIL Image object or None if not found
        """
        from PIL import Image, ImageOps
        try:
            validated = self._validate_filename(filename)
            path = self.get_image_path(validated, project_name)

            if not os.path.exists(path):
                return None

            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            return img
        except (ValueError, FileNotFoundError, Exception):
            return None

    def load_original(self, filename: str, project_name: str = None):
        """
        Load original image from backup.
        
        Returns:
            PIL Image object or None if not found
        """
        from PIL import Image, ImageOps
        try:
            validated = self._validate_filename(filename)
            path = self.get_original_path(validated, project_name)

            if not os.path.exists(path):
                return None

            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            return img
        except (ValueError, FileNotFoundError, Exception):
            return None

    # --- Файловые операции ---

    def save_image(self, filename: str, pil_image, project_name: str = None) -> bool:
        """
        Save PIL image to images folder.
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
            path = self.get_image_path(validated, project_name)
            pil_image.save(path)
            return True
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.save_image error: {e}")
            return False

    def save_original(self, filename: str, pil_image, project_name: str = None) -> bool:
        """
        Save PIL image to originals folder.
        
        Returns:
            True if saved successfully, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
            path = self.get_original_path(validated, project_name)
            pil_image.save(path)
            return True
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.save_original error: {e}")
            return False

    def copy_to_original(self, filename: str, project_name: str = None) -> bool:
        """
        Copy image from images to originals folder.
        
        Returns:
            True if copied successfully, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
            src = self.get_image_path(validated, project_name)
            dst = self.get_original_path(validated, project_name)

            if not os.path.exists(src):
                return False

            shutil.copy(src, dst)
            return True
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.copy_to_original error: {e}")
            return False

    def delete_image(self, filename: str, project_name: str = None) -> bool:
        """
        Delete image and original files.
        
        Returns:
            True if any file was deleted, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
            image_path = self.get_image_path(validated, project_name)
            original_path = self.get_original_path(validated, project_name)

            deleted = False

            if os.path.exists(image_path):
                os.remove(image_path)
                deleted = True

            if os.path.exists(original_path):
                os.remove(original_path)
                deleted = True

            return deleted
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.delete_image error: {e}")
            return False

    def list_images(self, project_name: str = None) -> list:
        """
        Get sorted list of image files.
        
        Returns:
            List of filenames
        """
        folder = self.get_image_folder(project_name)
        if not os.path.exists(folder):
            return []
        files = [f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in ALLOWED_EXTENSIONS]
        files.sort()
        return files

    # --- URL для фронтенда ---

    def get_image_url(self, filename: str, project_name: str = None, cache_bust: str = None) -> str:
        """
        Get URL for image to be used in frontend.
        
        Args:
            filename: Image filename
            project_name: Project name
            cache_bust: Optional cache busting parameter (timestamp)
            
        Returns:
            URL string for frontend
        """
        validated = self._validate_filename(filename)
        url = f"/data/images/{validated}"
        params = []
        if project_name:
            params.append(f"project={project_name}")
        if cache_bust:
            params.append(f"t={cache_bust}")
        if params:
            url += "?" + "&".join(params)
        return url

    def get_original_url(self, filename: str, project_name: str = None, cache_bust: str = None) -> str:
        """
        Get URL for original image to be used in frontend.

        Args:
            filename: Image filename
            project_name: Project name
            cache_bust: Optional cache busting parameter (timestamp)

        Returns:
            URL string for frontend
        """
        validated = self._validate_filename(filename)
        url = f"/data/originals/{validated}"
        params = []
        if project_name:
            params.append(f"project={project_name}")
        if cache_bust:
            params.append(f"t={cache_bust}")
        if params:
            url += "?" + "&".join(params)
        return url

    # --- Миниатюры ---

    def get_thumbnail_folder(self, project_name: str = None) -> str:
        """Get thumbnails folder path, optionally project-specific."""
        if project_name:
            folder = os.path.join(THUMBNAILS_FOLDER, project_name)
            os.makedirs(folder, exist_ok=True)
            return folder
        return THUMBNAILS_FOLDER

    def get_thumbnail_path(self, filename: str, project_name: str = None) -> str:
        """Get full path to thumbnail file."""
        validated = self._validate_filename(filename)
        folder = self.get_thumbnail_folder(project_name)
        name, _ = os.path.splitext(validated)
        return os.path.join(folder, f"{name}_thumb.jpg")

    def generate_thumbnail(self, filename: str, project_name: str = None, max_size: int = 300) -> bool:
        """
        Generate thumbnail for an image.

        Args:
            filename: Source image filename
            project_name: Project name
            max_size: Maximum width/height of thumbnail

        Returns:
            True if thumbnail was generated, False otherwise
        """
        from PIL import Image, ImageOps
        try:
            validated = self._validate_filename(filename)
            src_path = self.get_image_path(validated, project_name)

            if not os.path.exists(src_path):
                return False

            thumb_path = self.get_thumbnail_path(validated, project_name)

            img = Image.open(src_path)
            img = ImageOps.exif_transpose(img)

            # Конвертируем в RGB если RGBA/Grayscale (JPEG не поддерживает альфа)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            elif img.mode == 'L':
                img = img.convert('RGB')

            img.thumbnail((max_size, max_size), Image.LANCZOS)
            img.save(thumb_path, 'JPEG', quality=85, optimize=True)
            return True
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.generate_thumbnail error: {e}")
            return False

    def thumbnail_exists(self, filename: str, project_name: str = None) -> bool:
        """Check if thumbnail exists."""
        try:
            validated = self._validate_filename(filename)
            path = self.get_thumbnail_path(validated, project_name)
            return os.path.exists(path)
        except ValueError:
            return False

    def delete_thumbnail(self, filename: str, project_name: str = None) -> bool:
        """Delete thumbnail file."""
        try:
            validated = self._validate_filename(filename)
            thumb_path = self.get_thumbnail_path(validated, project_name)
            if os.path.exists(thumb_path):
                os.remove(thumb_path)
                return True
            return False
        except (ValueError, Exception) as e:
            print(f"ImageStorageService.delete_thumbnail error: {e}")
            return False

    def get_thumbnail_url(self, filename: str, project_name: str = None, cache_bust: str = None) -> str:
        """Get URL for thumbnail to be used in frontend."""
        validated = self._validate_filename(filename)
        name, _ = os.path.splitext(validated)
        thumb_name = f"{name}_thumb.jpg"
        url = f"/data/thumbnails/{thumb_name}"
        params = []
        if project_name:
            params.append(f"project={project_name}")
        if cache_bust:
            params.append(f"t={cache_bust}")
        if params:
            url += "?" + "&".join(params)
        return url

    # --- Утилиты ---

    def is_allowed_extension(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


# Global instance
image_storage_service = ImageStorageService()
