"""Project repository - CRUD operations for Project model."""

from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models import Project


class ProjectRepository:
    """Repository for Project CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(self, name: str, description: str = '') -> Project:
        """Create a new project."""
        project = Project(name=name, description=description)
        self.session.add(project)
        self.session.commit()
        self.session.refresh(project)
        return project
    
    def get_by_id(self, project_id: int) -> Optional[Project]:
        """Get project by ID."""
        return self.session.get(Project, project_id)
    
    def get_by_name(self, name: str) -> Optional[Project]:
        """Get project by name."""
        stmt = select(Project).where(Project.name == name)
        return self.session.execute(stmt).scalar_one_or_none()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[Project]:
        """Get all projects."""
        stmt = select(Project).offset(skip).limit(limit).order_by(Project.created_at.desc())
        return self.session.execute(stmt).scalars().all()
    
    def update(self, project: Project, name: Optional[str] = None, description: Optional[str] = None) -> Project:
        """Update project fields."""
        if name is not None:
            project.name = name
        if description is not None:
            project.description = description
        self.session.commit()
        self.session.refresh(project)
        return project
    
    def delete(self, project: Project) -> bool:
        """Delete project."""
        self.session.delete(project)
        self.session.commit()
        return True
    
    def count(self) -> int:
        """Get total number of projects."""
        stmt = select(Project)
        return self.session.execute(stmt).scalars().count()
