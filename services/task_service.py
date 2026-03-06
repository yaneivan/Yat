"""
Task Service for managing background operations.

Provides centralized task tracking, progress monitoring,
and automatic cleanup of completed tasks.
"""

import threading
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any, List
from sqlalchemy.orm import Session

from database.session import SessionLocal
from database.repository.task_repository import TaskRepository
from database.models import Task as TaskModel


class Task:
    """Represents a background task."""

    def __init__(
        self,
        task_id: str,
        task_type: str,
        project_name: str = "",
        images: List[str] = None,
        description: str = "",
        project_id: int = None
    ):
        self.id = task_id
        self.type = task_type
        self.project_name = project_name
        self.project_id = project_id
        self.images = images or []
        self.description = description
        self.status = "pending"  # pending, running, completed, failed
        self.progress = 0
        self.total = len(self.images)  # Использовать self.images вместо images
        self.completed = 0
        self.error = None
        self.created_at = datetime.now()
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """Convert task to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'type': self.type,
            'project_name': self.project_name,
            'project_id': self.project_id,
            'images': self.images,
            'description': self.description,
            'status': self.status,
            'progress': self.progress,
            'total': self.total,
            'completed': self.completed,
            'error': self.error,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


class TaskService:
    """
    Service for managing background tasks.

    Features:
    - Centralized task tracking
    - Progress monitoring
    - Automatic cleanup of old completed tasks
    - Thread-safe operations
    - Database persistence
    """

    CLEANUP_INTERVAL_MINUTES = 60

    def __init__(self):
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def _get_repo(self, session: Session = None):
        """Get task repository with session."""
        if session is None:
            session = SessionLocal()
        return TaskRepository(session), session

    def create_task(
        self,
        task_type: str,
        project_name: str = "",
        images: List[str] = None,
        description: str = "",
        project_id: int = None
    ) -> Task:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            project_name=project_name,
            images=images,
            description=description,
            project_id=project_id
        )

        # Also create in database
        repo, session = self._get_repo()
        try:
            repo.create(
                task_id=task_id,
                task_type=task_type,
                project_id=project_id,
                status='pending',
                progress=0
            )
        finally:
            session.close()

        return task

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID."""
        repo, session = self._get_repo()
        try:
            task_model = repo.get_by_id(task_id)
            if not task_model:
                return None
            
            # Convert DB model to Task object
            task = Task(
                task_id=task_model.id,
                task_type=task_model.type,
                project_name="",  # Not stored in DB
                project_id=task_model.project_id,
                images=[],  # Not stored in DB
                description=""  # Not stored in DB
            )
            task.status = task_model.status
            task.progress = task_model.progress
            task.completed = task_model.progress  # Approximation
            task.total = 100  # Fixed for DB-backed tasks
            task.error = task_model.result.get('error') if task_model.result else None
            return task
        finally:
            session.close()

    def get_all_tasks(self, status: str = None) -> List[Task]:
        """Get all tasks, optionally filtered by status."""
        repo, session = self._get_repo()
        try:
            task_models = repo.get_all(status=status)
            tasks = []
            for task_model in task_models:
                task = Task(
                    task_id=task_model.id,
                    task_type=task_model.type,
                    project_name="",
                    project_id=task_model.project_id,
                    images=[],
                    description=""
                )
                task.status = task_model.status
                task.progress = task_model.progress
                task.completed = task_model.progress
                task.total = 100
                task.error = task_model.result.get('error') if task_model.result else None
                tasks.append(task)
            return tasks
        finally:
            session.close()

    def update_progress(
        self,
        task_id: str,
        completed: int,
        status: str = None,
        error: str = None
    ) -> Optional[Task]:
        """Update the progress of a task."""
        repo, session = self._get_repo()
        try:
            task_model = repo.get_by_id(task_id)
            if not task_model:
                return None

            progress = int((completed / max(completed, 1)) * 100) if completed > 0 else 0
            result = task_model.result.copy() if task_model.result else {}
            if error:
                result['error'] = error

            repo.update(
                task_model,
                status=status,
                progress=progress,
                result=result
            )

            # Return Task object
            task = Task(
                task_id=task_id,
                task_type=task_model.type,
                project_name="",
                project_id=task_model.project_id
            )
            task.status = status or task_model.status
            task.progress = progress
            task.completed = completed
            task.error = error
            return task
        finally:
            session.close()

    def complete_task(self, task_id: str) -> Optional[Task]:
        """Mark a task as completed."""
        repo, session = self._get_repo()
        try:
            task_model = repo.get_by_id(task_id)
            if not task_model:
                return None

            repo.complete(task_model)

            task = Task(
                task_id=task_id,
                task_type=task_model.type,
                project_name="",
                project_id=task_model.project_id
            )
            task.status = 'completed'
            task.progress = 100
            task.completed = task.total
            return task
        finally:
            session.close()

    def fail_task(self, task_id: str, error: str) -> Optional[Task]:
        """Mark a task as failed."""
        repo, session = self._get_repo()
        try:
            task_model = repo.get_by_id(task_id)
            if not task_model:
                return None

            repo.fail(task_model, error)

            task = Task(
                task_id=task_id,
                task_type=task_model.type,
                project_name="",
                project_id=task_model.project_id
            )
            task.status = 'failed'
            task.progress = 0
            task.error = error
            return task
        finally:
            session.close()

    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        repo, session = self._get_repo()
        try:
            task_model = repo.get_by_id(task_id)
            if not task_model:
                return False
            return repo.delete(task_model)
        finally:
            session.close()
    
    def cleanup_completed(self, older_than_minutes: int = None) -> int:
        """Remove completed tasks older than specified minutes."""
        # DB-backed tasks are cleaned up via repository if needed
        # For now, just return 0 since DB handles persistence
        return 0

    def _cleanup_loop(self):
        """Background thread that periodically cleans up old tasks."""
        # Disabled for DB-backed tasks
        while True:
            threading.Event().wait(self.CLEANUP_INTERVAL_MINUTES * 60)
    
    def run_background(
        self,
        task: Task,
        func: Callable,
        *args,
        progress_callback: Callable = None,
        **kwargs
    ) -> threading.Thread:
        """
        Run a function in background with task tracking.
        
        Args:
            task: The task to track progress
            func: The function to run
            *args: Arguments to pass to the function
            progress_callback: Optional callback(current, total) for progress updates
            **kwargs: Keyword arguments to pass to the function
        
        Returns:
            The background thread
        """
        def wrapper():
            try:
                self.update_progress(task.id, 0, status="running")
                
                # Create a progress callback that updates the task
                def task_progress_callback(current: int, total: int):
                    self.update_progress(task.id, current)
                    if progress_callback:
                        progress_callback(current, total)
                
                # Run the function
                func(*args, **kwargs)
                
                # Mark as completed
                self.update_progress(task.id, task.total, status="completed")
                
            except Exception as e:
                self.fail_task(task.id, str(e))
        
        thread = threading.Thread(target=wrapper, daemon=True)
        thread.start()
        return thread


# Global task service instance
task_service = TaskService()
