"""
Annotation Service for managing image annotations.

Provides centralized access to annotation data with validation
and automatic field initialization.

Uses database for storage instead of JSON files.
"""

import os
import re
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session

from database.session import SessionLocal
from database.repository.annotation_repository import AnnotationRepository
from database.repository.image_repository import ImageRepository


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

    def get_annotation(self, filename: str) -> Dict[str, Any]:
        """
        Get annotation data for an image.

        Args:
            filename: The image filename

        Returns:
            Annotation dictionary with regions, texts, crop_params, etc.
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image by filename
            image = image_repo.get_by_filename(validated_filename)
            if not image:
                return {'regions': [], 'texts': {}, 'image_name': validated_filename}
            
            # Find annotation
            annotation = annotation_repo.get_by_image(image.id)
            if not annotation:
                return {'regions': [], 'texts': {}, 'image_name': validated_filename}
            
            # Convert to old format for compatibility
            polygons = annotation.polygons or []
            regions = [p.get('points', []) for p in polygons]
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

    def save_annotation(self, filename: str, data: Dict[str, Any]) -> bool:
        """
        Save annotation data for an image.

        Args:
            filename: The image filename
            data: Annotation data dictionary

        Returns:
            True if saved successfully, False otherwise
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image
            image = image_repo.get_by_filename(validated_filename)
            if not image:
                return False
            
            # Find or create annotation
            annotation = annotation_repo.get_by_image(image.id)
            
            # Convert regions and texts to polygons format
            regions = data.get('regions', [])
            texts = data.get('texts', {})
            polygons = []
            
            for i, region in enumerate(regions):
                polygon = {
                    'points': region,
                    'text': texts.get(str(i), texts.get(i, ''))
                }
                polygons.append(polygon)
            
            # Also accept polygons directly
            if 'polygons' in data:
                polygons = data['polygons']
            
            if annotation:
                annotation_repo.update(annotation, polygons=polygons)
            else:
                annotation_repo.create(image_id=image.id, polygons=polygons)
            
            return True
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

    def delete_annotation(self, filename: str) -> bool:
        """
        Delete annotation for an image.

        Args:
            filename: The image filename

        Returns:
            True if deleted successfully, False if annotation didn't exist
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            # Find image
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

    def get_status(self, filename: str) -> str:
        """
        Get the status of an image based on its annotation.

        Args:
            filename: The image filename

        Returns:
            Status string: 'crop', 'cropped', 'segment', or 'texted'
        """
        validated_filename = self._validate_filename(filename)
        
        session, annotation_repo, image_repo = self._get_session()
        try:
            image = image_repo.get_by_filename(validated_filename)
            if not image:
                return 'crop'
            
            if image.status == 'texted':
                return 'texted'
            
            annotation = annotation_repo.get_by_image(image.id)
            if annotation and annotation.polygons:
                return 'segment'
            
            if image.status == 'cropped':
                return 'cropped'
            
            return 'crop'
        finally:
            session.close()

    def get_all_annotations(self) -> List[Dict[str, Any]]:
        """
        Get all annotations with their filenames.

        Returns:
            List of dictionaries with 'filename' and annotation data
        """
        session, annotation_repo, image_repo = self._get_session()
        try:
            result = []
            images = image_repo.get_all(skip=0, limit=1000)
            
            for image in images:
                try:
                    data = self.get_annotation(image.filename)
                    data['filename'] = image.filename
                    result.append(data)
                except Exception:
                    # Skip files with invalid annotations
                    pass
            
            return result
        finally:
            session.close()


# Global annotation service instance
annotation_service = AnnotationService()
