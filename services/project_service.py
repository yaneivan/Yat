"""
Project Service for managing projects.

Provides centralized project operations with validation,
sanitization, and image management.

Uses database for storage instead of JSON files.
"""

import os
import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from database.session import SessionLocal
from database.repository.project_repository import ProjectRepository
from database.repository.image_repository import ImageRepository


class ProjectService:
    """
    Service for managing projects.

    Features:
    - Project name sanitization
    - CRUD operations
    - Image management within projects
    - Database-backed storage
    """

    # Characters not allowed in project names
    INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*]')

    def __init__(self):
        pass

    def _get_session(self) -> tuple:
        """Get database session and repositories."""
        session = SessionLocal()
        project_repo = ProjectRepository(session)
        image_repo = ImageRepository(session)
        return session, project_repo, image_repo

    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize project name.

        Args:
            name: Original project name

        Returns:
            Sanitized name
        """
        if not name:
            return ""

        # Replace invalid characters with underscore
        sanitized = self.INVALID_NAME_CHARS.sub('_', name)

        # Strip whitespace
        sanitized = sanitized.strip()

        return sanitized

    def create_project(self, name: str, description: str = '') -> Optional[Dict[str, Any]]:
        """
        Create a new project.

        Args:
            name: Project name
            description: Project description

        Returns:
            Project data dict if created, None if already exists
        """
        sanitized_name = self._sanitize_name(name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            # Check if project with same name exists
            existing = project_repo.get_by_name(sanitized_name)
            if existing:
                return None
            
            # Create project
            project = project_repo.create(name=sanitized_name, description=description)
            
            return {
                'name': project.name,
                'description': project.description,
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'images': []
            }
        finally:
            session.close()

    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get project data by name.

        Args:
            name: Project name

        Returns:
            Project data dict or None if not found
        """
        sanitized_name = self._sanitize_name(name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return None
            
            images = image_repo.get_by_project(project.id)
            
            return {
                'name': project.name,
                'description': project.description,
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'images': [img.to_dict() for img in images]
            }
        finally:
            session.close()

    def get_all_projects(self) -> List[Dict[str, Any]]:
        """Get all projects."""
        session, project_repo, image_repo = self._get_session()
        try:
            projects = project_repo.get_all()
            result = []
            
            for project in projects:
                images = image_repo.get_by_project(project.id)
                result.append({
                    'name': project.name,
                    'description': project.description,
                    'created_at': project.created_at.isoformat() if project.created_at else None,
                    'image_count': len(images),
                    'images': [img.to_dict() for img in images]
                })
            
            return result
        finally:
            session.close()

    def update_project(self, name: str, new_name: str = None, description: str = None) -> Optional[Dict[str, Any]]:
        """
        Update project name and/or description.

        Args:
            name: Current project name
            new_name: New project name (optional)
            description: New description (optional)

        Returns:
            Updated project data or None if not found
        """
        sanitized_name = self._sanitize_name(name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return None
            
            # Update fields
            updated_name = self._sanitize_name(new_name) if new_name else None
            
            # Check for name collision if renaming
            if updated_name and updated_name != sanitized_name:
                existing = project_repo.get_by_name(updated_name)
                if existing:
                    return None
                project = project_repo.update(project, name=updated_name)
            
            if description is not None:
                project = project_repo.update(project, description=description)
            
            images = image_repo.get_by_project(project.id)
            
            return {
                'name': project.name,
                'description': project.description,
                'created_at': project.created_at.isoformat() if project.created_at else None,
                'images': [img.to_dict() for img in images]
            }
        finally:
            session.close()

    def delete_project(self, name: str) -> bool:
        """
        Delete a project.

        Args:
            name: Project name

        Returns:
            True if deleted, False if not found
        """
        sanitized_name = self._sanitize_name(name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return False
            
            return project_repo.delete(project)
        finally:
            session.close()

    def add_image(
        self,
        project_name: str,
        filename: str,
        original_path: str,
        cropped_path: str = None,
        status: str = 'crop',
        crop_params: dict = None
    ) -> Optional[Dict[str, Any]]:
        """
        Add an image to a project.

        Args:
            project_name: Project name
            filename: Image filename
            original_path: Path to original image
            cropped_path: Path to cropped image
            status: Image status
            crop_params: Crop parameters

        Returns:
            Image data dict or None if failed
        """
        sanitized_name = self._sanitize_name(project_name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return None
            
            image = image_repo.create(
                project_id=project.id,
                filename=filename,
                original_path=original_path,
                cropped_path=cropped_path,
                status=status,
                crop_params=crop_params or {}
            )
            
            return image.to_dict()
        finally:
            session.close()

    def remove_image(self, project_name: str, filename: str) -> bool:
        """
        Remove an image from a project.

        Args:
            project_name: Project name
            filename: Image filename

        Returns:
            True if removed, False if not found
        """
        sanitized_name = self._sanitize_name(project_name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return False
            
            image = image_repo.get_by_filename(filename)
            if not image or image.project_id != project.id:
                return False
            
            return image_repo.delete(image)
        finally:
            session.close()

    def get_images(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Get all images in a project.

        Args:
            project_name: Project name

        Returns:
            List of image data dicts
        """
        sanitized_name = self._sanitize_name(project_name)
        
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return []
            
            images = image_repo.get_by_project(project.id)
            return [img.to_dict() for img in images]
        finally:
            session.close()

    def is_image_used_in_projects(self, filename: str) -> List[str]:
        """
        Check which projects use an image.

        Args:
            filename: Image filename

        Returns:
            List of project names using the image
        """
        session, project_repo, image_repo = self._get_session()
        try:
            image = image_repo.get_by_filename(filename)
            if not image:
                return []
            
            project = project_repo.get_by_id(image.project_id)
            if not project:
                return []
            
            return [project.name]
        finally:
            session.close()


# Global project service instance
project_service = ProjectService()
