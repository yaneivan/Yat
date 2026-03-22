"""
Annotation Service for managing image annotations.

Provides centralized access to annotation data with validation
and automatic field initialization.

Uses database for storage instead of JSON files.
"""

import re
from typing import Dict, List, Any

from database.session import SessionLocal
from database.repository.annotation_repository import AnnotationRepository
from database.repository.image_repository import ImageRepository
from database.enums import ImageStatus
from sqlalchemy.orm import Session


class AnnotationService:
    """
    Service for managing annotations.

    Features:
    - Filename validation and sanitization
    - Automatic field initialization
    - Centralized access to annotation data
    - Database-backed storage
    """

    # Pattern for valid filenames (security)
    VALID_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\u0400-\u04FF]+\.[a-zA-Z0-9]+$')

    def __init__(self):
        pass

    def _get_session(self) -> tuple:
        """Get database session and repositories."""
        session = SessionLocal()
        annotation_repo = AnnotationRepository(session)
        image_repo = ImageRepository(session)
        return session, annotation_repo, image_repo

    def _validate_filename(self, filename: str) -> str:
        """
        Validate and sanitize filename.

        Args:
            filename: The filename to validate

        Returns:
            Sanitized filename

        Raises:
            ValueError: If filename is invalid or contains path traversal
        """
        if not filename:
            raise ValueError("Filename cannot be empty")

        # Check for path traversal attempts
        if '..' in filename or '/' in filename or '\\' in filename:
            raise ValueError("Invalid filename: path traversal detected")

        # Check for valid characters
        if not self.VALID_FILENAME_PATTERN.match(filename):
            # Allow more permissive matching but log warning
            sanitized = re.sub(r'[<>:"|?*]', '_', filename)
            return sanitized

        return filename

    def get_annotation(self, filename: str, project_name: str = None) -> Dict[str, Any]:
        """
        Get annotation data for an image.

        Args:
            filename: The image filename
            project_name: Optional project name to scope the lookup

        Returns:
            Annotation dictionary with regions, texts, crop_params, etc.
        """
        validated_filename = self._validate_filename(filename)

        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image by filename (and project if provided)
            if project_name:
                image = image_repo.get_by_filename_and_project(validated_filename, project_name)
            else:
                image = image_repo.get_by_filename(validated_filename)
            
            if not image:
                return {
                    'regions': [],
                    'texts': {},
                    'image_name': validated_filename,
                    'crop_params': None
                }

            # Find annotation
            annotation = annotation_repo.get_by_image(image.id)
            if not annotation:
                return {
                    'regions': [],
                    'texts': {},
                    'image_name': validated_filename,
                    'crop_params': image.crop_params,
                    'status': image.status
                }

            # Convert to old format for compatibility
            polygons = annotation.polygons or []
            # Frontend ожидает {points: [...]}, а не просто [...]
            regions = [{'points': p.get('points', [])} for p in polygons]
            texts = {str(i): p.get('text', '') for i, p in enumerate(polygons)}

            return {
                'regions': regions,
                'texts': texts,
                'image_name': validated_filename,
                'crop_params': image.crop_params,
                'status': image.status,
                'polygons': polygons  # New format
            }
        finally:
            session.close()

    def save_annotation(self, filename: str, data: Dict[str, Any], project_name: str = None) -> bool:
        """
        Save annotation data for an image.

        Args:
            filename: The image filename
            data: Annotation data dictionary
            project_name: Optional project name to scope the lookup

        Returns:
            True if saved successfully, False otherwise
        """
        validated_filename = self._validate_filename(filename)

        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image (and project if provided)
            if project_name:
                image = image_repo.get_by_filename_and_project(validated_filename, project_name)
            else:
                image = image_repo.get_by_filename(validated_filename)
            
            if not image:
                print(f"[AnnotationService] Image not found: {filename}")
                return False

            # Update image fields (crop_params, status)
            if 'crop_params' in data:
                image_repo.update(image, crop_params=data['crop_params'])
            if 'status' in data:
                # Convert string status to ImageStatus enum if needed
                status_value = data['status']
                status_enum = ImageStatus(status_value) if isinstance(status_value, str) else status_value
                image_repo.update(image, status=status_enum)

            # Find or create annotation
            annotation = annotation_repo.get_by_image(image.id)
            print(f"[AnnotationService] Found annotation: {annotation is not None}")

            # Convert regions and texts to polygons format
            regions = data.get('regions', [])
            texts = data.get('texts', {})
            polygons = []

            for i, region in enumerate(regions):
                # Frontend отправляет {points: [...]}, извлекаем points
                points = region['points']
                polygon = {
                    'points': points,
                    'text': texts.get(str(i), texts.get(i, ''))
                }
                polygons.append(polygon)

            print(f"[AnnotationService] Saving {len(polygons)} polygons for {filename}")

            try:
                if annotation:
                    annotation_repo.update(annotation, polygons=polygons)
                    print("[AnnotationService] Updated existing annotation")
                else:
                    annotation_repo.create(image_id=image.id, polygons=polygons)
                    print("[AnnotationService] Created new annotation")
                return True
            except Exception as e:
                print(f"[AnnotationService] DB error: {e}")
                import traceback
                print(traceback.format_exc())
                return False
        finally:
            session.close()

    def update_fields(self, filename: str, **fields) -> Dict[str, Any]:
        """
        Update specific fields in an annotation.

        Args:
            filename: The image filename
            **fields: Fields to update (regions, texts, status, crop_params, etc.)

        Returns:
            Updated annotation data
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image
            image = image_repo.get_by_filename(validated_filename)
            if not image:
                return {}
            
            # Update image fields
            if 'status' in fields:
                image_repo.update(image, status=fields['status'])
            if 'crop_params' in fields:
                image_repo.update(image, crop_params=fields['crop_params'])
            
            # Update annotation fields
            annotation = annotation_repo.get_by_image(image.id)
            if annotation and 'regions' in fields:
                # Convert regions to polygons
                regions = fields['regions']
                texts = fields.get('texts', {})
                polygons = []
                for i, region in enumerate(regions):
                    polygon = {
                        'points': region,
                        'text': texts.get(str(i), texts.get(i, ''))
                    }
                    polygons.append(polygon)
                annotation_repo.update(annotation, polygons=polygons)
            
            # Return updated data
            return self.get_annotation(validated_filename)
        finally:
            session.close()

    def delete_annotation(self, filename: str, project_name: str = None) -> bool:
        """
        Delete annotation for an image.

        Args:
            filename: The image filename
            project_name: Optional project name to scope the lookup

        Returns:
            True if deleted successfully, False if annotation didn't exist
        """
        validated_filename = self._validate_filename(filename)

        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image (and project if provided)
            if project_name:
                image = image_repo.get_by_filename_and_project(validated_filename, project_name)
            else:
                image = image_repo.get_by_filename(validated_filename)
            
            if not image:
                return False

            # Find and delete annotation
            annotation = annotation_repo.get_by_image(image.id)
            if annotation:
                return annotation_repo.delete(annotation)
            return False
        finally:
            session.close()

    def has_annotation(self, filename: str) -> bool:
        """
        Check if an annotation exists for an image.

        Args:
            filename: The image filename

        Returns:
            True if annotation exists, False otherwise
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            image = image_repo.get_by_filename(validated_filename)
            if not image:
                return False
            
            annotation = annotation_repo.get_by_image(image.id)
            return annotation is not None
        finally:
            session.close()

    def get_status(self, filename: str, project_name: str = None) -> str:
        """
        Get the status of an image based on its annotation.

        Args:
            filename: The image filename
            project_name: Optional project name to scope the lookup

        Returns:
            Status string: 'uploaded', 'cropped', 'segmented', or 'recognized'
        """
        validated_filename = self._validate_filename(filename)

        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image (and project if provided)
            if project_name:
                image = image_repo.get_by_filename_and_project(validated_filename, project_name)
            else:
                image = image_repo.get_by_filename(validated_filename)
            
            if not image:
                return ImageStatus.UPLOADED.value

            if image.status == ImageStatus.RECOGNIZED.value:
                return ImageStatus.RECOGNIZED.value

            annotation = annotation_repo.get_by_image(image.id)
            if annotation and annotation.polygons:
                return ImageStatus.SEGMENTED.value

            if image.status == ImageStatus.CROPPED.value:
                return ImageStatus.CROPPED.value

            return ImageStatus.UPLOADED.value
        finally:
            session.close()

    def get_all_annotations(self) -> List[Dict[str, Any]]:
        """
        Get all annotations with their filenames (optimized query, no N+1).

        Returns:
            List of dictionaries with 'filename' and annotation data
        """
        session, annotation_repo, image_repo = self._get_session()
        try:
            # Получить ВСЕ изображения одним запросом
            images = image_repo.get_all(skip=0, limit=1000)
            
            # Получить ВСЕ аннотации одним запросом
            all_annotations = self._get_all_annotations_raw(session)
            
            # Сгруппировать аннотации по image_id в памяти
            annotations_by_image = {ann['image_id']: ann for ann in all_annotations}
            
            # Сформировать результат без дополнительных запросов к БД
            result = []
            for image in images:
                ann = annotations_by_image.get(image.id)
                
                # Конвертировать в формат совместимости
                if ann:
                    polygons = ann.get('polygons', [])
                    regions = [{'points': p.get('points', [])} for p in polygons]
                    texts = {str(i): p.get('text', '') for i, p in enumerate(polygons)}
                else:
                    regions = []
                    texts = {}
                
                result.append({
                    'filename': image.filename,
                    'regions': regions,
                    'texts': texts,
                    'image_name': image.filename,
                    'crop_params': image.crop_params,
                    'status': image.status,
                    'polygons': ann.get('polygons', []) if ann else []
                })

            return result
        finally:
            session.close()

    def _get_all_annotations_raw(self, session: Session) -> List[Dict[str, Any]]:
        """
        Get all annotations as raw dicts (for batch operations).

        Args:
            session: Database session

        Returns:
            List of annotation dicts
        """
        from database.models import Annotation
        
        annotations = session.query(Annotation).all()
        return [
            {
                'id': ann.id,
                'image_id': ann.image_id,
                'polygons': ann.polygons or []
            }
            for ann in annotations
        ]


# Global annotation service instance
annotation_service = AnnotationService()
