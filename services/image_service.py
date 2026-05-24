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

    ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}

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

    def get_image_path(self, filename: str, project_id: int = None) -> str:
        """Get full path to image in images folder."""
        return image_storage_service.get_image_path(filename, project_id)

    def get_original_path(self, filename: str, project_id: int = None) -> str:
        """Get full path to original image backup."""
        return image_storage_service.get_original_path(filename, project_id)

    def image_exists(self, filename: str, project_id: int = None) -> bool:
        """Check if image exists in images folder."""
        try:
            return image_storage_service.image_exists(filename, project_id)
        except ValueError:
            return False

    def original_exists(self, filename: str, project_id: int = None) -> bool:
        """Check if original backup exists."""
        try:
            return image_storage_service.original_exists(filename, project_id)
        except ValueError:
            return False

    def ensure_original_exists(self, filename: str, project_id: int = None) -> bool:
        """
        Ensure original backup exists, copy from images if needed.

        Args:
            filename: The image filename
            project_id: Optional project ID for project-specific path

        Returns:
            True if original exists or was copied, False otherwise
        """
        return image_storage_service.ensure_original_exists(filename, project_id)

    def get_image(self, filename: str, project_id: int = None) -> Optional[Image.Image]:
        """
        Load image from images folder.

        Args:
            filename: The image filename
            project_id: Optional project ID for project-specific path

        Returns:
            PIL Image object or None if not found
        """
        return image_storage_service.load_image(filename, project_id)

    def get_original(
        self, filename: str, project_id: int = None
    ) -> Optional[Image.Image]:
        """
        Load original image from backup.

        Args:
            filename: The image filename
            project_id: Optional project ID for project-specific path

        Returns:
            PIL Image object or None if not found
        """
        return image_storage_service.load_original(filename, project_id)

    def crop_image(
        self,
        filename: str,
        box: Dict[str, Any],
        project_id: int = None,
        update_regions: bool = True,
    ) -> bool:
        """
        Crop an image using the specified box.

        Args:
            filename: The image filename
            box: Crop box with 'corners' array [TL, BL, BR, TR]
            project_id: Project ID for project-specific file paths
            update_regions: Whether to recalculate regions

        Returns:
            True if crop was successful, False otherwise
        """
        try:
            validated = self._validate_filename(filename)

            if not self.ensure_original_exists(validated, project_id):
                return False

            annotation_data = annotation_service.get_annotation(validated, project_id)
            old_crop = annotation_data.get("crop_params")
            old_regions = annotation_data.get("regions", [])

            original_path = self.get_original_path(validated, project_id)
            with Image.open(original_path) as img:
                img = ImageOps.exif_transpose(img)

                corners = box["corners"]

                quad = [
                    corners[0]["x"],
                    corners[0]["y"],
                    corners[3]["x"],
                    corners[3]["y"],
                    corners[2]["x"],
                    corners[2]["y"],
                    corners[1]["x"],
                    corners[1]["y"],
                ]

                def dist(p1, p2):
                    return ((p1["x"] - p2["x"]) ** 2 + (p1["y"] - p2["y"]) ** 2) ** 0.5

                new_width = int(
                    (dist(corners[0], corners[1]) + dist(corners[3], corners[2])) / 2
                )
                new_height = int(
                    (dist(corners[0], corners[3]) + dist(corners[1], corners[2])) / 2
                )

                img_cropped = img.transform(
                    (new_width, new_height), Image.QUAD, quad, Image.BICUBIC
                )

                image_path = self.get_image_path(validated, project_id)
                img_cropped.save(image_path)

                image_storage_service.generate_thumbnail(validated, project_id)

            # Recalculate regions if needed
            if update_regions and old_regions:
                from logic import recalculate_regions

                new_regions = recalculate_regions(
                    old_regions, old_crop, corners, new_width, new_height
                )
                annotation_data["regions"] = new_regions

            # Update annotation
            annotation_data["crop_params"] = box
            annotation_data["status"] = ImageStatus.CROPPED.value
            annotation_data["image_name"] = validated
            annotation_service.save_annotation(validated, annotation_data, project_id)

            return True

        except Exception as e:
            print(f"ImageService.crop_image error: {e}")
            return False

    def upload_image(
        self,
        file_storage,
        project_id: Optional[int] = None,
    ) -> Optional[str]:
        """
        Upload an image file.

        Args:
            file_storage: Flask FileStorage object
            project_id: Optional project ID to add image to

        Returns:
            Filename if successful, None otherwise
        """
        if not file_storage or not file_storage.filename:
            return None

        filename = file_storage.filename

        if not self.is_allowed_extension(filename):
            return None

        try:
            image_path = self.get_image_path(filename, project_id)
            file_storage.save(image_path)

            original_path = self.get_original_path(filename, project_id)
            shutil.copy(image_path, original_path)

            image_storage_service.generate_thumbnail(filename, project_id)

            if project_id:
                session, image_repo, project_repo = self._get_session()
                try:
                    project = project_repo.get_by_id(project_id)

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
                            status=ImageStatus.UPLOADED,
                        )
                finally:
                    session.close()

            return filename

        except Exception as e:
            print(f"ImageService.upload_image error: {e}")
            return None

    def delete_image(
        self, filename: str, project_id: int = None, skip_project_check: bool = False
    ) -> bool:
        """
        Delete an image and its annotation.

        Args:
            filename: The image filename
            project_id: Project ID for project-specific paths
            skip_project_check: Skip checking if image is used in projects

        Returns:
            True if deleted, False otherwise
        """
        try:
            validated = self._validate_filename(filename)

            if not skip_project_check:
                session, image_repo, project_repo = self._get_session()
                try:
                    image = image_repo.get_by_filename_and_project_id(
                        validated, project_id
                    )
                    if image:
                        return False
                finally:
                    session.close()

            image_path = self.get_image_path(validated, project_id)
            original_path = self.get_original_path(validated, project_id)

            deleted = False

            if os.path.exists(image_path):
                os.remove(image_path)
                deleted = True

            if os.path.exists(original_path):
                os.remove(original_path)
                deleted = True

            image_storage_service.delete_thumbnail(validated, project_id)

            annotation_service.delete_annotation(validated, project_id)

            return deleted

        except (ValueError, Exception) as e:
            print(f"ImageService.delete_image error: {e}")
            return False

    def get_all_images(self, project_id: int = None) -> List[Dict[str, Any]]:
        """
        Get all images with their status (optimized query, no N+1).

        Args:
            project_id: Optional project ID to filter images

        Returns:
            List of dictionaries with 'name' and 'status' fields
        """
        session, image_repo, project_repo = self._get_session()
        try:
            if project_id:
                project = project_repo.get_by_id(project_id)
                if not project:
                    return []
                images = image_repo.get_by_project(project.id)
            else:
                images = image_repo.get_all()

            all_annotations = annotation_service._get_all_annotations_raw(session)

            all_projects = project_repo.get_all()
            project_name_by_id = {p.id: p.name for p in all_projects}

            annotations_by_image = {ann["image_id"]: ann for ann in all_annotations}

            result = []
            for image in images:
                ann = annotations_by_image.get(image.id)
                if ann and ann.get("polygons"):
                    status = ImageStatus.SEGMENTED.value
                elif image.status == ImageStatus.RECOGNIZED.value:
                    status = ImageStatus.RECOGNIZED.value
                elif image.status == ImageStatus.CROPPED.value:
                    status = ImageStatus.CROPPED.value
                else:
                    status = ImageStatus.UPLOADED.value

                result.append(
                    {
                        "id": image.id,
                        "name": image.filename,
                        "status": status,
                        "project_id": image.project_id,
                        "project_name": project_name_by_id.get(image.project_id),
                    }
                )

            return result
        finally:
            session.close()

    def get_images_by_project(self, project_id: int) -> List[Dict[str, Any]]:
        """
        Get all images in a specific project with their status.

        Args:
            project_id: The ID of the project

        Returns:
            List of dictionaries with 'name' and 'status' fields
        """
        session, image_repo, project_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return []

            images = image_repo.get_by_project(project.id)

            result = []
            for image in images:
                result.append(
                    {
                        "id": image.id,
                        "name": image.filename,
                        "status": image.status or ImageStatus.UPLOADED.value,
                        "project_id": image.project_id,
                    }
                )

            return result
        finally:
            session.close()

    def is_image_used_in_other_projects(
        self, filename: str, exclude_project: Optional[str] = None
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
                "status": image.status,
                "comment": image.comment,
                "reviewed_at": image.reviewed_at.isoformat()
                if image.reviewed_at
                else None,
            }
        finally:
            session.close()

    def update_status(
        self,
        filename: str,
        project_name: str,
        status: Optional[str] = None,
        comment: Optional[str] = None,
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
            if status == "reviewed":
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
