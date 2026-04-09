"""
Image Service for managing images.

Provides centralized image operations with validation,
file management, and project integration.

Files are managed by ImageStorageService, this service handles:
- Business logic (crop, upload with checks)
- Database integration
- Project coordination
"""

import os
import shutil
from typing import Optional, List, Dict, Any
from PIL import Image, ImageOps

from database.session import SessionLocal
from database.repository.image_repository import ImageRepository
from database.repository.project_repository import ProjectRepository
from database.enums import ImageStatus
from services.annotation_service import annotation_service
from services.image_storage_service import image_storage_service


class ImageService:
    """
    Service for managing images.

    Features:
    - Image validation
    - Automatic backup to originals
    - Crop operations with region recalculation
    - Project integration checks
    
    File operations are delegated to ImageStorageService.
    """

    ALLOWED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'}

    def __init__(self):
        pass

    def _get_session(self) -> tuple:
        """Get database session and repositories."""
        session = SessionLocal()
        image_repo = ImageRepository(session)
        project_repo = ProjectRepository(session)
        return session, image_repo, project_repo

    def _validate_filename(self, filename: str) -> str:
        """Validate filename for security."""
        return image_storage_service._validate_filename(filename)

    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        return os.path.splitext(filename)[1].lower()

    def is_allowed_extension(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return image_storage_service.is_allowed_extension(filename)

    def get_image_path(self, filename: str, project_name: str = None) -> str:
        """Get full path to image in images folder."""
        return image_storage_service.get_image_path(filename, project_name)

    def get_original_path(self, filename: str, project_name: str = None) -> str:
        """Get full path to original image backup."""
        return image_storage_service.get_original_path(filename, project_name)

    def image_exists(self, filename: str) -> bool:
        """Check if image exists in images folder."""
        try:
            return image_storage_service.image_exists(filename)
        except ValueError:
            return False

    def original_exists(self, filename: str) -> bool:
        """Check if original backup exists."""
        try:
            return image_storage_service.original_exists(filename)
        except ValueError:
            return False

    def ensure_original_exists(self, filename: str, project_name: str = None) -> bool:
        """
        Ensure original backup exists, copy from images if needed.

        Args:
            filename: The image filename
            project_name: Optional project name for project-specific path

        Returns:
            True if original exists or was copied, False otherwise
        """
        return image_storage_service.ensure_original_exists(filename, project_name)

    def get_image(self, filename: str, project_name: str = None) -> Optional[Image.Image]:
        """
        Load image from images folder.

        Args:
            filename: The image filename
            project_name: Optional project name for project-specific path

        Returns:
            PIL Image object or None if not found
        """
        return image_storage_service.load_image(filename, project_name)

    def get_original(self, filename: str, project_name: str = None) -> Optional[Image.Image]:
        """
        Load original image from backup.

        Args:
            filename: The image filename
            project_name: Optional project name for project-specific path

        Returns:
            PIL Image object or None if not found
        """
        return image_storage_service.load_original(filename, project_name)

    def crop_image(
        self,
        filename: str,
        box: Dict[str, Any],
        project_name: str = None,
        update_regions: bool = True
    ) -> bool:
        """
        Crop an image using the specified box.

        Args:
            filename: The image filename
            box: Crop box with 'corners' array [TL, BL, BR, TR]
            project_name: Project name for project-specific file paths
            update_regions: Whether to recalculate regions

        Returns:
            True if crop was successful, False otherwise
        """
        try:
            validated = self._validate_filename(filename)

            # Ensure original exists for this project
            if not self.ensure_original_exists(validated, project_name):
                return False

            # Load current annotation data with project scope
            annotation_data = annotation_service.get_annotation(validated, project_name)
            old_crop = annotation_data.get('crop_params')
            old_regions = annotation_data.get('regions', [])

            # Get original image from project-specific folder
            original_path = self.get_original_path(validated, project_name)
            with Image.open(original_path) as img:
                img = ImageOps.exif_transpose(img)

                corners = box['corners']

                # Pillow QUAD format: TL, BL, BR, TR
                quad = [
                    corners[0]['x'], corners[0]['y'],  # TL
                    corners[3]['x'], corners[3]['y'],  # BL
                    corners[2]['x'], corners[2]['y'],  # BR
                    corners[1]['x'], corners[1]['y']   # TR
                ]

                # Calculate new dimensions
                def dist(p1, p2):
                    return ((p1['x'] - p2['x'])**2 + (p1['y'] - p2['y'])**2)**0.5

                new_width = int((dist(corners[0], corners[1]) + dist(corners[3], corners[2])) / 2)
                new_height = int((dist(corners[0], corners[3]) + dist(corners[1], corners[2])) / 2)

                # Crop the image
                img_cropped = img.transform(
                    (new_width, new_height),
                    Image.QUAD,
                    quad,
                    Image.BICUBIC
                )

                # Save cropped image to project-specific folder
                image_path = self.get_image_path(validated, project_name)
                img_cropped.save(image_path)

                # Regenerate thumbnail for cropped image
                image_storage_service.generate_thumbnail(validated, project_name)

            # Recalculate regions if needed
            if update_regions and old_regions:
                from logic import recalculate_regions
                new_regions = recalculate_regions(
                    old_regions,
                    old_crop,
                    corners,
                    new_width,
                    new_height
                )
                annotation_data['regions'] = new_regions

            # Update annotation
            annotation_data['crop_params'] = box
            annotation_data['status'] = ImageStatus.CROPPED.value
            annotation_data['image_name'] = validated
            annotation_service.save_annotation(validated, annotation_data, project_name)

            return True

        except Exception as e:
            print(f"ImageService.crop_image error: {e}")
            return False

    def upload_image(
        self,
        file_storage,
        project_name: Optional[str] = None,
        project_id: Optional[int] = None
    ) -> Optional[str]:
        """
        Upload an image file.

        Args:
            file_storage: Flask FileStorage object
            project_name: Optional project name to add image to
            project_id: Optional project ID (alternative to project_name)

        Returns:
            Filename if successful, None otherwise
        """
        if not file_storage or not file_storage.filename:
            return None

        filename = file_storage.filename

        # Validate extension
        if not self.is_allowed_extension(filename):
            return None

        try:
            # Save to project-specific images folder
            image_path = self.get_image_path(filename, project_name)
            file_storage.save(image_path)

            # Copy to project-specific originals folder
            original_path = self.get_original_path(filename, project_name)
            shutil.copy(image_path, original_path)

            # Generate thumbnail
            image_storage_service.generate_thumbnail(filename, project_name)

            # Add to project if specified
            if project_name or project_id:
                session, image_repo, project_repo = self._get_session()
                try:
                    # Find project
                    if project_id:
                        project = project_repo.get_by_id(project_id)
                    else:
                        project = project_repo.get_by_name(project_name)

                    if project:
                        # Check for duplicate filename
                        existing_images = image_repo.get_by_project(project.id)
                        for img in existing_images:
                            if img.filename == filename:
                                # Duplicate found - skip this file
                                return None

                        image_repo.create(
                            project_id=project.id,
                            filename=filename,
                            original_path=original_path,
                            cropped_path=image_path,
                            status=ImageStatus.UPLOADED
                        )
                finally:
                    session.close()

            return filename

        except Exception as e:
            print(f"ImageService.upload_image error: {e}")
            return None

    def delete_image(
        self,
        filename: str,
        project_name: str = None,
        skip_project_check: bool = False
    ) -> bool:
        """
        Delete an image and its annotation.

        Args:
            filename: The image filename
            project_name: Project name for project-specific paths
            skip_project_check: Skip checking if image is used in projects

        Returns:
            True if deleted, False otherwise
        """
        try:
            validated = self._validate_filename(filename)

            # Check if image is used in other projects (skip if flag is set)
            if not skip_project_check:
                session, image_repo, project_repo = self._get_session()
                try:
                    image = image_repo.get_by_filename(validated)
                    if image:
                        # Image is in DB - don't delete if it's in a project
                        return False
                finally:
                    session.close()

            # Delete project-specific image files
            image_path = self.get_image_path(validated, project_name)
            original_path = self.get_original_path(validated, project_name)

            deleted = False

            if os.path.exists(image_path):
                os.remove(image_path)
                deleted = True

            if os.path.exists(original_path):
                os.remove(original_path)
                deleted = True

            # Delete thumbnail
            image_storage_service.delete_thumbnail(validated, project_name)

            # Delete annotation (DB will cascade)
            annotation_service.delete_annotation(validated, project_name)

            return deleted

        except (ValueError, Exception) as e:
            print(f"ImageService.delete_image error: {e}")
            return False

    def get_all_images(self, project_name: str = None) -> List[Dict[str, Any]]:
        """
        Get all images with their status (optimized query, no N+1).

        Args:
            project_name: Optional project name to filter images

        Returns:
            List of dictionaries with 'name' and 'status' fields
        """
        session, image_repo, project_repo = self._get_session()
        try:
            # Получить ВСЕ изображения (или для конкретного проекта) одним запросом
            if project_name:
                project = project_repo.get_by_name(project_name)
                if not project:
                    return []
                images = image_repo.get_by_project(project.id)
            else:
                images = image_repo.get_all()

            # Получить ВСЕ аннотации одним запросом (вместо N запросов)
            all_annotations = annotation_service._get_all_annotations_raw(session)

            # Получить ВСЕ проекты для маппинга project_id -> project_name
            all_projects = project_repo.get_all()
            project_name_by_id = {p.id: p.name for p in all_projects}

            # Сгруппировать аннотации по image_id в памяти
            annotations_by_image = {ann['image_id']: ann for ann in all_annotations}

            # Сформировать результат без дополнительных запросов к БД
            result = []
            for image in images:
                # Получить статус из памяти, а не из БД
                ann = annotations_by_image.get(image.id)
                if ann and ann.get('polygons'):
                    status = ImageStatus.SEGMENTED.value
                elif image.status == ImageStatus.RECOGNIZED.value:
                    status = ImageStatus.RECOGNIZED.value
                elif image.status == ImageStatus.CROPPED.value:
                    status = ImageStatus.CROPPED.value
                else:
                    status = ImageStatus.UPLOADED.value

                result.append({
                    'id': image.id,
                    'name': image.filename,
                    'status': status,
                    'project_id': image.project_id,
                    'project_name': project_name_by_id.get(image.project_id)
                })

            return result
        finally:
            session.close()

    def get_images_by_project(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Get all images in a specific project with their status.

        Args:
            project_name: The name of the project

        Returns:
            List of dictionaries with 'name' and 'status' fields
        """
        session, image_repo, project_repo = self._get_session()
        try:
            project = project_repo.get_by_name(project_name)
            if not project:
                return []

            images = image_repo.get_by_project(project.id)

            result = []
            for image in images:
                result.append({
                    'id': image.id,
                    'name': image.filename,
                    'status': image.status or ImageStatus.UPLOADED.value,
                    'project_id': image.project_id
                })

            return result
        finally:
            session.close()

    def is_image_used_in_other_projects(
        self,
        filename: str,
        exclude_project: Optional[str] = None
    ) -> bool:
        """
        Check if image is used in other projects.

        Args:
            filename: The image filename
            exclude_project: Project name to exclude from check

        Returns:
            True if used in other projects, False otherwise
        """
        session, image_repo, project_repo = self._get_session()
        try:
            image = image_repo.get_by_filename(filename)
            if not image:
                return False
            
            # Image exists in DB, so it's in a project
            return True
        finally:
            session.close()

    def get_status(self, filename: str, project_name: str) -> Optional[Dict[str, Any]]:
        """
        Get image status and comment.

        Args:
            filename: The image filename
            project_name: The project name

        Returns:
            Dict with status, comment, reviewed_at or None if not found
        """
        session, image_repo, _ = self._get_session()
        try:
            image = image_repo.get_by_filename_and_project(filename, project_name)
            if not image:
                return None
            
            return {
                'status': image.status,
                'comment': image.comment,
                'reviewed_at': image.reviewed_at.isoformat() if image.reviewed_at else None
            }
        finally:
            session.close()

    def update_status(
        self,
        filename: str,
        project_name: str,
        status: Optional[str] = None,
        comment: Optional[str] = None
    ) -> bool:
        """
        Update image status and/or comment.

        Args:
            filename: The image filename
            project_name: The project name
            status: New status value (optional)
            comment: New comment value (optional)

        Returns:
            True if updated, False if image not found
        """
        from datetime import datetime
        
        session, image_repo, _ = self._get_session()
        try:
            image = image_repo.get_by_filename_and_project(filename, project_name)
            if not image:
                return False
            
            # Update fields
            if status:
                image.status = status
            if comment is not None:
                image.comment = comment
            
            # Set review timestamp when status changes to reviewed
            if status == 'reviewed':
                image.reviewed_at = datetime.utcnow()
            
            image.updated_at = datetime.utcnow()
            session.commit()
            
            return True
        except Exception:
            session.rollback()
            return False
        finally:
            session.close()


# Global image service instance
image_service = ImageService()
