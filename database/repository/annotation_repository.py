"""Annotation repository - CRUD operations for Annotation model."""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models import Annotation


class AnnotationRepository:
    """Repository for Annotation CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, image_id: int, polygons: Optional[list] = None) -> Annotation:
        """Create a new annotation."""
        annotation = Annotation(image_id=image_id, polygons=polygons or [])
        self.session.add(annotation)
        self.session.commit()
        self.session.refresh(annotation)
        return annotation
    
    def get_by_id(self, annotation_id: int) -> Optional[Annotation]:
        """Get annotation by ID."""
        return self.session.get(Annotation, annotation_id)
    
    def get_by_image(self, image_id: int) -> Optional[Annotation]:
        """Get annotation for a specific image."""
        stmt = select(Annotation).where(Annotation.image_id == image_id)
        return self.session.execute(stmt).scalar_one_or_none()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[Annotation]:
        """Get all annotations."""
        stmt = select(Annotation).offset(skip).limit(limit).order_by(Annotation.created_at.desc())
        return self.session.execute(stmt).scalars().all()
    
    def update(self, annotation: Annotation, polygons: Optional[list] = None) -> Annotation:
        """Update annotation."""
        if polygons is not None:
            annotation.polygons = polygons
        self.session.commit()
        self.session.refresh(annotation)
        return annotation
    
    def delete(self, annotation: Annotation) -> bool:
        """Delete annotation."""
        self.session.delete(annotation)
        self.session.commit()
        return True
    
    def count(self) -> int:
        """Get total number of annotations."""
        stmt = select(Annotation)
        return self.session.execute(stmt).scalars().count()
