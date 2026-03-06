"""
Annotation Service for managing image annotations.

Provides centralized access to annotation data with validation
and automatic field initialization.
"""

import os
import re
from typing import Dict, List, Any, Optional

import storage


class AnnotationService:
    """
    Service for managing annotations.
    
    Features:
    - Filename validation and sanitization
    - Automatic field initialization
    - Centralized access to annotation data
    """
    
    # Pattern for valid filenames (security)
    VALID_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.\u0400-\u04FF]+\.[a-zA-Z0-9]+$')
    
    def __init__(self):
        pass
    
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
        return storage.load_json(validated_filename)
    
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
        
        # Ensure required fields exist
        if 'image_name' not in data:
            data['image_name'] = validated_filename
        
        if 'texts' not in data:
            data['texts'] = {}
        
        if 'regions' not in data:
            data['regions'] = []
        
        return storage.save_json(data)
    
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
        
        # Load existing data
        data = self.get_annotation(validated_filename)
        
        # Update specified fields
        for key, value in fields.items():
            data[key] = value
        
        # Ensure image_name is set
        data['image_name'] = validated_filename
        
        # Save and return
        self.save_annotation(validated_filename, data)
        return data
    
    def delete_annotation(self, filename: str) -> bool:
        """
        Delete annotation for an image.
        
        Args:
            filename: The image filename
        
        Returns:
            True if deleted successfully, False if annotation didn't exist
        """
        validated_filename = self._validate_filename(filename)
        
        annotation_path = os.path.join(
            storage.ANNOTATION_FOLDER,
            os.path.splitext(validated_filename)[0] + '.json'
        )
        
        if os.path.exists(annotation_path):
            os.remove(annotation_path)
            return True
        
        return False
    
    def has_annotation(self, filename: str) -> bool:
        """
        Check if an annotation exists for an image.
        
        Args:
            filename: The image filename
        
        Returns:
            True if annotation exists, False otherwise
        """
        validated_filename = self._validate_filename(filename)
        
        annotation_path = os.path.join(
            storage.ANNOTATION_FOLDER,
            os.path.splitext(validated_filename)[0] + '.json'
        )
        
        return os.path.exists(annotation_path)
    
    def get_status(self, filename: str) -> str:
        """
        Get the status of an image based on its annotation.
        
        Args:
            filename: The image filename
        
        Returns:
            Status string: 'crop', 'cropped', 'segment', or 'texted'
        """
        validated_filename = self._validate_filename(filename)
        
        annotation_path = os.path.join(
            storage.ANNOTATION_FOLDER,
            os.path.splitext(validated_filename)[0] + '.json'
        )
        
        if not os.path.exists(annotation_path):
            return 'crop'
        
        data = self.get_annotation(validated_filename)
        
        if data.get('status') == 'texted':
            return 'texted'
        elif data.get('regions'):
            return 'segment'
        elif data.get('status') == 'cropped':
            return 'cropped'
        else:
            return 'crop'
    
    def get_all_annotations(self) -> List[Dict[str, Any]]:
        """
        Get all annotations with their filenames.
        
        Returns:
            List of dictionaries with 'filename' and annotation data
        """
        result = []
        
        for filename in storage.get_sorted_images():
            try:
                data = self.get_annotation(filename)
                data['filename'] = filename
                result.append(data)
            except Exception:
                # Skip files with invalid annotations
                pass
        
        return result


# Global annotation service instance
annotation_service = AnnotationService()
