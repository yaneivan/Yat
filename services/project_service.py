"""
Project Service for managing projects.

Provides centralized project operations with validation,
sanitization, and image management.
"""

import os
import json
import re
import shutil
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

import storage


class ProjectService:
    """
    Service for managing projects.
    
    Features:
    - Project name sanitization
    - CRUD operations
    - Image management within projects
    - Export functionality
    """
    
    # Characters not allowed in directory names
    INVALID_NAME_CHARS = re.compile(r'[<>:"/\\|?*]')
    
    def __init__(self):
        pass
    
    def _sanitize_name(self, name: str) -> str:
        """
        Sanitize project name for use as directory name.
        
        Args:
            name: Original project name
        
        Returns:
            Sanitized name safe for filesystem
        """
        if not name:
            return ""
        
        # Replace invalid characters with underscore
        sanitized = self.INVALID_NAME_CHARS.sub('_', name)
        
        # Strip whitespace
        sanitized = sanitized.strip()
        
        return sanitized
    
    def _get_project_path(self, name: str) -> str:
        """Get full path to project directory."""
        sanitized = self._sanitize_name(name)
        return os.path.join(storage.PROJECTS_FOLDER, sanitized)
    
    def _get_project_json_path(self, name: str) -> str:
        """Get full path to project.json file."""
        return os.path.join(self._get_project_path(name), 'project.json')
    
    def _project_exists(self, name: str) -> bool:
        """Check if project exists."""
        return os.path.exists(self._get_project_json_path(name))
    
    def _load_project_data(self, name: str) -> Optional[Dict[str, Any]]:
        """Load project data from JSON file."""
        project_path = self._get_project_json_path(name)
        
        if not os.path.exists(project_path):
            return None
        
        with open(project_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _save_project_data(self, name: str, data: Dict[str, Any]) -> bool:
        """Save project data to JSON file."""
        try:
            project_path = self._get_project_json_path(name)
            
            with open(project_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            
            return True
        except Exception:
            return False
    
    def create_project(
        self,
        name: str,
        description: str = ""
    ) -> Tuple[bool, Any]:
        """
        Create a new project.
        
        Args:
            name: Project name
            description: Project description
        
        Returns:
            Tuple of (success, result_or_error_message)
        """
        # Validate name
        if not name or not name.strip():
            return False, "Project name cannot be empty"
        
        sanitized = self._sanitize_name(name)
        
        if not sanitized:
            return False, "Invalid project name"
        
        # Check if already exists
        if self._project_exists(sanitized):
            return False, "Project already exists"
        
        try:
            # Create directory
            project_path = self._get_project_path(name)
            os.makedirs(project_path, exist_ok=True)
            
            # Create project data
            project_data = {
                'name': name,  # Keep original name in data
                'description': description,
                'created_at': datetime.now().isoformat(),
                'images': []
            }
            
            # Save project data
            if self._save_project_data(sanitized, project_data):
                return True, project_data
            else:
                return False, "Failed to save project data"
                
        except Exception as e:
            return False, f"Error creating project: {str(e)}"
    
    def get_project(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get project details.
        
        Args:
            name: Project name
        
        Returns:
            Project data dictionary or None if not found
        """
        return self._load_project_data(name)
    
    def update_project(
        self,
        name: str,
        new_name: Optional[str] = None,
        description: Optional[str] = None
    ) -> Tuple[bool, Any]:
        """
        Update project details.
        
        Args:
            name: Current project name
            new_name: New project name (optional)
            description: New description (optional)
        
        Returns:
            Tuple of (success, result_or_error_message)
        """
        # Load current data
        project_data = self._load_project_data(name)
        
        if not project_data:
            return False, "Project not found"
        
        sanitized_old = self._sanitize_name(name)
        
        # Handle name change
        if new_name and new_name != name:
            sanitized_new = self._sanitize_name(new_name)
            
            if not sanitized_new:
                return False, "Invalid new project name"
            
            # Check if new name already exists
            if self._project_exists(sanitized_new):
                return False, "Project with this name already exists"
            
            # Rename directory
            old_path = self._get_project_path(name)
            new_path = os.path.join(storage.PROJECTS_FOLDER, sanitized_new)
            
            try:
                os.rename(old_path, new_path)
            except OSError as e:
                return False, f"Failed to rename project: {str(e)}"
            
            # Update name in data
            project_data['name'] = new_name
            sanitized_old = sanitized_new
        
        # Update description if provided
        if description is not None:
            project_data['description'] = description
        
        # Save updated data
        if self._save_project_data(sanitized_old, project_data):
            return True, project_data
        else:
            return False, "Failed to save project data"
    
    def delete_project(self, name: str) -> Tuple[bool, str]:
        """
        Delete a project.
        
        Args:
            name: Project name
        
        Returns:
            Tuple of (success, message)
        """
        project_path = self._get_project_path(name)
        
        if not os.path.exists(project_path):
            return False, "Project does not exist"
        
        try:
            shutil.rmtree(project_path)
            return True, "Project deleted successfully"
        except Exception as e:
            return False, f"Error deleting project: {str(e)}"
    
    def get_all_projects(self) -> List[Dict[str, Any]]:
        """
        Get list of all projects.
        
        Returns:
            List of project data dictionaries
        """
        projects = []
        
        for project_dir in os.listdir(storage.PROJECTS_FOLDER):
            project_path = os.path.join(storage.PROJECTS_FOLDER, project_dir)
            
            if os.path.isdir(project_path):
                project_json = os.path.join(project_path, 'project.json')
                
                if os.path.exists(project_json):
                    with open(project_json, 'r', encoding='utf-8') as f:
                        projects.append(json.load(f))
        
        return projects
    
    def get_images(self, project_name: str) -> List[Dict[str, Any]]:
        """
        Get all images in a project with status.
        
        Args:
            project_name: Project name
        
        Returns:
            List of image dictionaries with 'name' and 'status'
        """
        project_data = self._load_project_data(project_name)
        
        if not project_data:
            return []
        
        images_data = project_data.get('images', [])
        result = []
        
        for img in images_data:
            if isinstance(img, dict):
                # Already has name and status
                result.append(img)
            else:
                # Just a filename string - get status
                from services.annotation_service import annotation_service
                status = annotation_service.get_status(img)
                result.append({'name': img, 'status': status})
        
        return result
    
    def add_image(
        self,
        project_name: str,
        image_name: str
    ) -> Tuple[bool, Any]:
        """
        Add an image to a project.
        
        Args:
            project_name: Project name
            image_name: Image filename
        
        Returns:
            Tuple of (success, result_or_error_message)
        """
        project_data = self._load_project_data(project_name)
        
        if not project_data:
            return False, "Project does not exist"
        
        images = project_data.get('images', [])
        
        # Check if already in project (handle both dict and string formats)
        for img in images:
            existing_name = img['name'] if isinstance(img, dict) else img
            if existing_name == image_name:
                return False, "Image already in project"
        
        # Add image with status
        from services.annotation_service import annotation_service
        status = annotation_service.get_status(image_name)
        images.append({'name': image_name, 'status': status})
        
        project_data['images'] = images
        
        if self._save_project_data(project_name, project_data):
            return True, project_data
        else:
            return False, "Failed to save project data"
    
    def remove_image(
        self,
        project_name: str,
        image_name: str,
        delete_file: bool = False
    ) -> Tuple[bool, Any]:
        """
        Remove an image from a project.
        
        Args:
            project_name: Project name
            image_name: Image filename
            delete_file: Whether to delete the actual file
        
        Returns:
            Tuple of (success, result_or_error_message)
        """
        project_data = self._load_project_data(project_name)
        
        if not project_data:
            return False, "Project does not exist"
        
        images = project_data.get('images', [])
        image_found = False
        
        # Remove image (handle both dict and string formats)
        for img in images[:]:
            existing_name = img['name'] if isinstance(img, dict) else img
            if existing_name == image_name:
                images.remove(img)
                image_found = True
                break
        
        if not image_found:
            return False, "Image not in project"
        
        project_data['images'] = images
        
        # Save updated project
        if not self._save_project_data(project_name, project_data):
            return False, "Failed to save project data"
        
        # Delete file if requested and not used in other projects
        if delete_file:
            if not self.is_image_used_in_projects(image_name, exclude_project=project_name):
                from services.image_service import image_service
                image_service.delete_image(image_name, skip_project_check=True)
        
        return True, project_data
    
    def is_image_used_in_projects(
        self,
        image_name: str,
        exclude_project: Optional[str] = None
    ) -> bool:
        """
        Check if an image is used in any project.
        
        Args:
            image_name: Image filename
            exclude_project: Project name to exclude from check
        
        Returns:
            True if used in other projects, False otherwise
        """
        projects = self.get_all_projects()
        
        for project in projects:
            project_name = project.get('name', '')
            
            # Skip excluded project
            if exclude_project and project_name == exclude_project:
                continue
            
            images = project.get('images', [])
            
            for img in images:
                existing_name = img['name'] if isinstance(img, dict) else img
                if existing_name == image_name:
                    return True
        
        return False
    
    def export_to_zip(self, project_name: str) -> Optional[bytes]:
        """
        Export project to ZIP archive.
        
        Args:
            project_name: Project name
        
        Returns:
            ZIP file bytes or None if export failed
        """
        import zipfile
        import io
        import xml.etree.ElementTree as ET
        from PIL import Image
        
        project_data = self._load_project_data(project_name)
        
        if not project_data:
            return None
        
        images = self.get_images(project_name)
        
        memory_file = io.BytesIO()
        
        try:
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for image_item in images:
                    image_name = image_item['name']
                    
                    from services.image_service import image_service
                    image_path = image_service.get_image_path(image_name)
                    
                    if not os.path.exists(image_path):
                        continue
                    
                    # Add image to zip
                    zipf.write(image_path, image_name)
                    
                    # Create PAGE XML annotation
                    annotation_name = os.path.splitext(image_name)[0] + '.xml'
                    
                    from services.annotation_service import annotation_service
                    annotation_data = annotation_service.get_annotation(image_name)
                    
                    # Create PAGE XML structure
                    root = ET.Element(
                        'PcGts',
                        xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"
                    )
                    page = ET.SubElement(root, 'Page', imageFilename=image_name)
                    
                    # Get image dimensions
                    try:
                        with Image.open(image_path) as img:
                            w, h = img.size
                    except:
                        w, h = 0, 0
                    
                    page.set('imageWidth', str(w))
                    page.set('imageHeight', str(h))
                    
                    # Add text regions and lines
                    text_region = ET.SubElement(page, 'TextRegion', id='r1')
                    
                    regions = annotation_data.get('regions', [])
                    texts = annotation_data.get('texts', {})
                    
                    for i, reg in enumerate(regions):
                        points = reg.get('points', [])
                        if points:
                            pts_str = " ".join([f"{p['x']},{p['y']}" for p in points])
                            
                            text_line = ET.SubElement(text_region, 'TextLine', id=f'l{i}')
                            ET.SubElement(text_line, 'Coords', points=pts_str)
                            
                            # Add text if available
                            text_key = str(i)
                            if text_key in texts and texts[text_key]:
                                text_equiv = ET.SubElement(text_line, 'TextEquiv')
                                ET.SubElement(text_equiv, 'Unicode').text = texts[text_key]
                    
                    # Write XML to archive
                    xml_content = ET.tostring(root, encoding='utf-8')
                    zipf.writestr(annotation_name, xml_content)
                
                # Add project metadata
                project_json_path = self._get_project_json_path(project_name)
                if os.path.exists(project_json_path):
                    zipf.write(project_json_path, 'project.json')
            
            memory_file.seek(0)
            return memory_file.getvalue()
            
        except Exception as e:
            print(f"ProjectService.export_to_zip error: {e}")
            return None


# Global project service instance
project_service = ProjectService()
