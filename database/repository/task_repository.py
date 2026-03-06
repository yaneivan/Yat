"""Task repository - CRUD operations for Task model."""

from typing import Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from database.models import Task


class TaskRepository:
    """Repository for Task CRUD operations."""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        task_id: str,
        task_type: str,
        project_id: Optional[int] = None,
        status: str = 'pending',
        progress: int = 0,
        result: Optional[dict] = None
    ) -> Task:
        """Create a new task."""
        task = Task(
            id=task_id,
            type=task_type,
            project_id=project_id,
            status=status,
            progress=progress,
            result=result or {}
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task
    
    def get_by_id(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.session.get(Task, task_id)
    
    def get_all(self, status: Optional[str] = None, limit: int = 50) -> List[Task]:
        """Get all tasks, optionally filtered by status."""
        stmt = select(Task)
        if status:
            stmt = stmt.where(Task.status == status)
        stmt = stmt.order_by(Task.created_at.desc()).limit(limit)
        return self.session.execute(stmt).scalars().all()
    
    def update(
        self,
        task: Task,
        status: Optional[str] = None,
        progress: Optional[int] = None,
        result: Optional[dict] = None
    ) -> Task:
        """Update task fields."""
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if result is not None:
            task.result = result
        self.session.commit()
        self.session.refresh(task)
        return task
    
    def complete(self, task: Task, result: Optional[dict] = None) -> Task:
        """Mark task as completed."""
        task.status = 'completed'
        task.progress = 100
        task.completed_at = datetime.utcnow()
        if result is not None:
            task.result = result
        self.session.commit()
        self.session.refresh(task)
        return task
    
    def fail(self, task: Task, error: str) -> Task:
        """Mark task as failed."""
        task.status = 'failed'
        task.result = {'error': error}
        task.completed_at = datetime.utcnow()
        self.session.commit()
        self.session.refresh(task)
        return task
    
    def delete(self, task: Task) -> bool:
        """Delete task."""
        self.session.delete(task)
        self.session.commit()
        return True
    
    def get_pending_tasks(self) -> List[Task]:
        """Get all pending tasks."""
        return self.get_all(status='pending')
    
    def get_running_tasks(self) -> List[Task]:
        """Get all running tasks."""
        return self.get_all(status='running')
