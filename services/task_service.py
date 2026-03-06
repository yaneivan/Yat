"""
Task Service for managing background operations.

Provides centralized task tracking, progress monitoring,
and automatic cleanup of completed tasks.
"""

import threading
import uuid
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any, List


class Task:
    """Represents a background task."""
    
    def __init__(
        self,
        task_id: str,
        task_type: str,
        project_name: str = "",
        images: List[str] = None,
        description: str = ""
    ):
        self.id = task_id
        self.type = task_type
        self.project_name = project_name
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
    """
    
    CLEANUP_INTERVAL_MINUTES = 60
    
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def create_task(
        self,
        task_type: str,
        project_name: str = "",
        images: List[str] = None,
        description: str = ""
    ) -> Task:
        """Create a new background task."""
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            project_name=project_name,
            images=images,
            description=description
        )
        
        with self._lock:
            self._tasks[task_id] = task
        
        return task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get a specific task by ID."""
        with self._lock:
            return self._tasks.get(task_id)
    
    def get_all_tasks(self, status: str = None) -> List[Task]:
        """Get all tasks, optionally filtered by status."""
        with self._lock:
            tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return tasks
    
    def update_progress(
        self,
        task_id: str,
        completed: int,
        status: str = None,
        error: str = None
    ) -> Optional[Task]:
        """Update the progress of a task."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            
            task.completed = completed
            if task.total > 0:
                task.progress = int((completed / task.total) * 100)
            else:
                task.progress = 0
            task.updated_at = datetime.now()
            
            if status:
                task.status = status
            
            if error:
                task.error = error
        
        return task
    
    def complete_task(self, task_id: str) -> Optional[Task]:
        """Mark a task as completed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            
            task.completed = task.total
            if task.total > 0:
                task.progress = 100
            else:
                task.progress = 0
            task.status = "completed"
            task.updated_at = datetime.now()
            
            return task
    
    def fail_task(self, task_id: str, error: str) -> Optional[Task]:
        """Mark a task as failed."""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            
            task.completed = 0
            task.progress = 0
            task.status = "failed"
            task.error = error
            task.updated_at = datetime.now()
            
            return task
    
    def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
    
    def cleanup_completed(self, older_than_minutes: int = None) -> int:
        """Remove completed tasks older than specified minutes."""
        if older_than_minutes is None:
            older_than_minutes = self.CLEANUP_INTERVAL_MINUTES
        
        cutoff = datetime.now() - timedelta(minutes=older_than_minutes)
        removed = 0
        
        with self._lock:
            to_remove = [
                task_id for task_id, task in self._tasks.items()
                if task.status in ("completed", "failed") and task.updated_at < cutoff
            ]
            
            for task_id in to_remove:
                del self._tasks[task_id]
                removed += 1
        
        return removed
    
    def _cleanup_loop(self):
        """Background thread that periodically cleans up old tasks."""
        while True:
            threading.Event().wait(self.CLEANUP_INTERVAL_MINUTES * 60)
            self.cleanup_completed()
    
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
