"""
Image Service for managing images.

Provides centralized image operations with validation,
file management, and project integration.

Files are stored on disk, metadata in database.
"""

import os
import shutil
from typing import Optional, List, Dict, Any
from PIL import Image, ImageOps

from database.session import SessionLocal
from database.repository.image_repository import ImageRepository
from database.repository.project_repository import ProjectRepository
from services.annotation_service import annotation_service


class ImageService:
    """
    Service for managing images.

    Features:
    - Image validation
    - Automatic backup to originals
    - Crop operations with region recalculation
    - Project integration checks
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
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Check for path traversal
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError("Invalid filename: path traversal detected")

        return filename

    def _get_extension(self, filename: str) -> str:
        """Get lowercase file extension."""
        return os.path.splitext(filename)[1].lower()

    def is_allowed_extension(self, filename: str) -> bool:
        """Check if file extension is allowed."""
        return self._get_extension(filename) in self.ALLOWED_EXTENSIONS

    def get_image_path(self, filename: str) -> str:
        """Get full path to image in images folder."""
        from storage import IMAGE_FOLDER
        validated = self._validate_filename(filename)
        return os.path.join(IMAGE_FOLDER, validated)

    def get_original_path(self, filename: str) -> str:
        """Get full path to original image backup."""
        from storage import ORIGINALS_FOLDER
        validated = self._validate_filename(filename)
        return os.path.join(ORIGINALS_FOLDER, validated)

    def image_exists(self, filename: str) -> bool:
        """Check if image exists in images folder."""
        try:
            validated = self._validate_filename(filename)
            path = self.get_image_path(validated)
            return os.path.exists(path)
        except ValueError:
            return False

    def original_exists(self, filename: str) -> bool:
        """Check if original backup exists."""
        try:
            validated = self._validate_filename(filename)
            path = self.get_original_path(validated)
            return os.path.exists(path)
        except ValueError:
            return False

    def ensure_original_exists(self, filename: str) -> bool:
        """
        Ensure original backup exists, copy from images if needed.

        Args:
            filename: The image filename

        Returns:
            True if original exists or was copied, False otherwise
        """
        try:
            validated = self._validate_filename(filename)
        except ValueError:
            return False

        src = self.get_image_path(validated)
        dst = self.get_original_path(validated)

        if not os.path.exists(dst) and os.path.exists(src):
            shutil.copy(src, dst)

        return os.path.exists(dst)

    def get_image(self, filename: str) -> Optional[Image.Image]:
        """
        Load image from images folder.

        Args:
            filename: The image filename

        Returns:
            PIL Image object or None if not found
        """
        try:
            validated = self._validate_filename(filename)
            path = self.get_image_path(validated)

            if not os.path.exists(path):
                return None

            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            return img
        except (ValueError, FileNotFoundError, Exception):
            return None

    def get_original(self, filename: str) -> Optional[Image.Image]:
        """
        Load original image from backup.

        Args:
            filename: The image filename

        Returns:
            PIL Image object or None if not found
        """
        try:
            validated = self._validate_filename(filename)
            path = self.get_original_path(validated)

            if not os.path.exists(path):
                return None

            img = Image.open(path)
            img = ImageOps.exif_transpose(img)
            return img
        except (ValueError, FileNotFoundError, Exception):
            return None

    def crop_image(
        self,
        filename: str,
        box: Dict[str, Any],
        update_regions: bool = True
    ) -> bool:
        """
        Crop an image using the specified box.

        Args:
            filename: The image filename
            box: Crop box with 'corners' array [TL, BL, BR, TR]
            update_regions: Whether to recalculate regions

        Returns:
            True if crop was successful, False otherwise
        """
        try:
            validated = self._validate_filename(filename)

            # Ensure original exists
            if not self.ensure_original_exists(validated):
                return False

            # Load current annotation data
            annotation_data = annotation_service.get_annotation(validated)
            old_crop = annotation_data.get('crop_params')
            old_regions = annotation_data.get('regions', [])

            # Get original image
            original_path = self.get_original_path(validated)
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

                # Save cropped image
                image_path = self.get_image_path(validated)
                img_cropped.save(image_path)

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
            annotation_data['status'] = 'cropped'
            annotation_data['image_name'] = validated
            annotation_service.save_annotation(validated, annotation_data)

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
            # Save to images folder
            image_path = self.get_image_path(filename)
            file_storage.save(image_path)

            # Copy to originals folder
            shutil.copy(image_path, self.get_original_path(filename))

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
                        image_repo.create(
                            project_id=project.id,
                            filename=filename,
                            original_path=self.get_original_path(filename),
                            cropped_path=image_path,
                            status='crop'
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
        skip_project_check: bool = False
    ) -> bool:
        """
        Delete an image and its annotation.

        Args:
            filename: The image filename
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

            # Delete image files
            image_path = self.get_image_path(validated)
            original_path = self.get_original_path(validated)

            deleted = False

            if os.path.exists(image_path):
                os.remove(image_path)
                deleted = True

            if os.path.exists(original_path):
                os.remove(original_path)
                deleted = True

            # Delete annotation (DB will cascade)
            annotation_service.delete_annotation(validated)

            return deleted

        except (ValueError, Exception) as e:
            print(f"ImageService.delete_image error: {e}")
            return False

    def get_all_images(self) -> List[Dict[str, Any]]:
        """
        Get all images with their status.

        Returns:
            List of dictionaries with 'name' and 'status' fields
        """
        session, image_repo, project_repo = self._get_session()
        try:
            result = []
            images = image_repo.get_all()
            
            for image in images:
                status = annotation_service.get_status(image.filename)
                result.append({
                    'id': image.id,
                    'name': image.filename,
                    'status': status,
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


# Global image service instance
image_service = ImageService()
