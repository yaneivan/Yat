"""Enums for the application."""

from enum import Enum


class ImageStatus(str, Enum):
    """Status values for images in the annotation workflow."""

    UPLOADED = 'uploaded'   # Image uploaded, needs cropping
    CROPPED = 'cropped'     # Cropped, ready for segmentation
    SEGMENTED = 'segmented' # Polygons drawn, ready for text recognition
    RECOGNIZED = 'recognized'  # Text recognized by AI
    REVIEWED = 'reviewed'   # Reviewed and approved


class TaskStatus(str, Enum):
    """Status values for background tasks."""

    PENDING = 'pending'     # Task created, waiting to start
    RUNNING = 'running'     # Task is executing
    COMPLETED = 'completed' # Task finished successfully
    FAILED = 'failed'       # Task failed with error


class UserRole(str, Enum):
    """User roles for access control."""

    ADMIN = 'admin'     # Full access: manage users, projects, annotations
    ANNOTATOR = 'annotator'  # Can annotate and edit assigned projects
    REVIEWER = 'reviewer'    # Can review and approve, read-only otherwise
