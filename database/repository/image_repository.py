"""Image repository - CRUD operations for Image model."""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models import Image
from database.enums import ImageStatus


class ImageRepository:
    """Repository for Image CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        project_id: int,
        filename: str,
        original_path: str,
        cropped_path: Optional[str] = None,
        status: ImageStatus = ImageStatus.UPLOADED,
        crop_params: Optional[dict] = None
    ) -> Image:
        """Create a new image."""
        image = Image(
            project_id=project_id,
            filename=filename,
            original_path=original_path,
            cropped_path=cropped_path,
            status=status.value,
            crop_params=crop_params or {}
        )
        self.session.add(image)
        self.session.commit()
        self.session.refresh(image)
        return image
    
    def get_by_id(self, image_id: int) -> Optional[Image]:
        """Get image by ID."""
        return self.session.get(Image, image_id)
    
    def get_by_filename(self, filename: str) -> Optional[Image]:
        """Get image by filename. Returns first match if duplicates exist."""
        stmt = select(Image).where(Image.filename == filename)
        return self.session.execute(stmt).scalars().first()

    def get_by_filename_and_project(self, filename: str, project_name: str) -> Optional[Image]:
        """Get image by filename and project name."""
        from database.models import Project
        stmt = (
            select(Image)
            .join(Project)
            .where(Image.filename == filename)
            .where(Project.name == project_name)
        )
        return self.session.execute(stmt).scalars().first()

    def get_by_project(self, project_id: int) -> List[Image]:
        """Get all images in a project."""
        stmt = select(Image).where(Image.project_id == project_id).order_by(Image.created_at)
        return self.session.execute(stmt).scalars().all()

    def get_all(self, skip: int = 0, limit: int = 1000) -> List[Image]:
        """Get all images."""
        stmt = select(Image).offset(skip).limit(limit).order_by(Image.created_at)
        return self.session.execute(stmt).scalars().all()

    def update(
        self,
        image: Image,
        filename: Optional[str] = None,
        cropped_path: Optional[str] = None,
        status: Optional[ImageStatus] = None,
        crop_params: Optional[dict] = None
    ) -> Image:
        """Update image fields."""
        if filename is not None:
            image.filename = filename
        if cropped_path is not None:
            image.cropped_path = cropped_path
        if status is not None:
            image.status = status.value
        if crop_params is not None:
            image.crop_params = crop_params
        self.session.commit()
        self.session.refresh(image)
        return image
    
    def delete(self, image: Image) -> bool:
        """Delete image."""
        self.session.delete(image)
        self.session.commit()
        return True
