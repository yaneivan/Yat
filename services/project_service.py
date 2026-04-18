"""
Project Service for managing projects.

Provides centralized project operations with validation,
sanitization, and image management.

Uses database for storage instead of JSON files.
"""

import os
import re
from typing import Dict, List, Any, Optional

from database.session import SessionLocal
from database.repository.project_repository import ProjectRepository
from database.repository.image_repository import ImageRepository

from services.image_storage_service import image_storage_service
from services.annotation_service import annotation_service


class ProjectService:
    """
    Service for managing projects.

    Features:
    - Project CRUD operations
    - Image management within projects
    - Database-backed storage
    """

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
        if not name:
            return ""
        sanitized = self.INVALID_NAME_CHARS.sub("_", name)
        sanitized = sanitized.strip()
        return sanitized

    def create_project(
        self, name: str, description: str = ""
    ) -> Optional[Dict[str, Any]]:
        sanitized_name = self._sanitize_name(name)

        session, project_repo, image_repo = self._get_session()
        try:
            existing = project_repo.get_by_name(sanitized_name)
            if existing:
                return None

            project = project_repo.create(name=sanitized_name, description=description)

            return {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat()
                if project.created_at
                else None,
                "images": [],
            }
        finally:
            session.close()

    def get_project(self, project_id: int) -> Optional[Dict[str, Any]]:
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return None

            images = image_repo.get_by_project(project.id)

            return {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat()
                if project.created_at
                else None,
                "images": [img.to_dict() for img in images],
            }
        finally:
            session.close()

    def get_project_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        sanitized_name = self._sanitize_name(name)

        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_name(sanitized_name)
            if not project:
                return None

            images = image_repo.get_by_project(project.id)

            return {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat()
                if project.created_at
                else None,
                "images": [img.to_dict() for img in images],
            }
        finally:
            session.close()

    def get_all_projects(self) -> List[Dict[str, Any]]:
        session, project_repo, image_repo = self._get_session()
        try:
            projects = project_repo.get_all()

            all_images = image_repo.get_all()

            images_by_project = {}
            for img in all_images:
                if img.project_id not in images_by_project:
                    images_by_project[img.project_id] = []
                images_by_project[img.project_id].append(img)

            result = []
            for project in projects:
                images = images_by_project.get(project.id, [])
                result.append(
                    {
                        "id": project.id,
                        "name": project.name,
                        "description": project.description,
                        "created_at": project.created_at.isoformat()
                        if project.created_at
                        else None,
                        "image_count": len(images),
                        "images": [img.to_dict() for img in images],
                    }
                )

            return result
        finally:
            session.close()

    def update_project(
        self, project_id: int, new_name: str = None, description: str = None
    ) -> Optional[Dict[str, Any]]:
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return None

            updated_name = self._sanitize_name(new_name) if new_name else None

            if updated_name and updated_name != project.name:
                existing = project_repo.get_by_name(updated_name)
                if existing:
                    return None
                project = project_repo.update(project, name=updated_name)

            if description is not None:
                project = project_repo.update(project, description=description)

            images = image_repo.get_by_project(project.id)

            return {
                "id": project.id,
                "name": project.name,
                "description": project.description,
                "created_at": project.created_at.isoformat()
                if project.created_at
                else None,
                "images": [img.to_dict() for img in images],
            }
        finally:
            session.close()

    def delete_project(self, project_id: int) -> bool:
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return False

            from database.repository.task_repository import TaskRepository

            task_repo = TaskRepository(session)
            tasks = task_repo.get_all()
            for task in tasks:
                if task.project_id == project.id:
                    task_repo.delete(task)

            return project_repo.delete(project)
        finally:
            session.close()

    def add_image(
        self,
        project_id: int,
        filename: str,
        original_path: str,
        cropped_path: str = None,
        status: str = "uploaded",
        crop_params: dict = None,
    ) -> Optional[Dict[str, Any]]:
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return None

            existing_images = image_repo.get_by_project(project.id)
            for img in existing_images:
                if img.filename == filename:
                    return None

            image = image_repo.create(
                project_id=project.id,
                filename=filename,
                original_path=original_path,
                cropped_path=cropped_path,
                status=status,
                crop_params=crop_params or {},
            )

            return image.to_dict()
        finally:
            session.close()

    def remove_image(self, project_id: int, filename: str) -> bool:
        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return False

            image = image_repo.get_by_filename_and_project_id(filename, project_id)
            if not image:
                return False

            return image_repo.delete(image)
        finally:
            session.close()

    def get_images(self, project_id: int) -> List[Dict[str, Any]]:
        from services.image_storage_service import image_storage_service

        session, project_repo, image_repo = self._get_session()
        try:
            project = project_repo.get_by_id(project_id)
            if not project:
                return []

            images = image_repo.get_by_project(project.id)
            result = []
            for img in images:
                data = img.to_dict()
                data["thumbnail_url"] = image_storage_service.get_thumbnail_url(
                    img.filename, project.name
                )
                result.append(data)
            return result
        finally:
            session.close()

    def get_image_by_filename(
        self, filename: str, project_id: int
    ) -> Optional[Dict[str, Any]]:
        session, project_repo, image_repo = self._get_session()
        try:
            image = image_repo.get_by_filename_and_project_id(filename, project_id)
            if not image:
                return None
            return image.to_dict()
        finally:
            session.close()

    def is_image_used_in_projects(self, filename: str) -> List[int]:
        session, project_repo, image_repo = self._get_session()
        try:
            image = image_repo.get_by_filename(filename)
            if not image:
                return []

            project = project_repo.get_by_id(image.project_id)
            if not project:
                return []

            return [project.id]
        finally:
            session.close()

    def export_to_zip(self, project_id: int) -> Optional[bytes]:
        import zipfile
        import io
        import xml.etree.ElementTree as ET
        from PIL import Image

        project_data = self.get_project(project_id)

        if not project_data:
            return None

        project_name = project_data["name"]
        images = self.get_images(project_id)

        memory_file = io.BytesIO()

        try:
            with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zipf:
                for image_item in images:
                    image_name = image_item["filename"]

                    image_path = image_storage_service.get_image_path(
                        image_name, project_name
                    )

                    if not os.path.exists(image_path):
                        continue

                    zipf.write(image_path, image_name)

                    annotation_name = os.path.splitext(image_name)[0] + ".xml"

                    annotation_data = annotation_service.get_annotation(
                        image_name, project_name
                    )

                    root = ET.Element(
                        "PcGts",
                        xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15",
                    )
                    page = ET.SubElement(root, "Page", imageFilename=image_name)

                    try:
                        with Image.open(image_path) as img:
                            w, h = img.size
                    except Exception:
                        w, h = 0, 0

                    page.set("imageWidth", str(w))
                    page.set("imageHeight", str(h))

                    text_region = ET.SubElement(page, "TextRegion", id="r1")

                    regions = annotation_data.get("regions", [])
                    texts = annotation_data.get("texts", {})

                    for i, reg in enumerate(regions):
                        points = (
                            reg.get("points", reg) if isinstance(reg, dict) else reg
                        )
                        if points:
                            pts_str = " ".join([f"{p['x']},{p['y']}" for p in points])

                            text_line = ET.SubElement(
                                text_region, "TextLine", id=f"l{i}"
                            )
                            ET.SubElement(text_line, "Coords", points=pts_str)

                            text_key = str(i)
                            if text_key in texts and texts[text_key]:
                                text_equiv = ET.SubElement(text_line, "TextEquiv")
                                ET.SubElement(text_equiv, "Unicode").text = texts[
                                    text_key
                                ]

                    xml_content = ET.tostring(root, encoding="utf-8")
                    zipf.writestr(annotation_name, xml_content)

            memory_file.seek(0)
            return memory_file.getvalue()

        except Exception as e:
            print(f"ProjectService.export_to_zip error: {e}")
            import traceback

            traceback.print_exc()
            return None


# Global project service instance
project_service = ProjectService()
