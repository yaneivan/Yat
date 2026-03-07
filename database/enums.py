"""Enums for the application."""

from enum import Enum


class ImageStatus(str, Enum):
    """Status values for images in the annotation workflow."""
    
    CROP = 'crop'           # Image uploaded, needs cropping
    CROPPED = 'cropped'     # Cropped, ready for segmentation
    SEGMENT = 'segment'     # Polygons drawn, ready for text recognition
    TEXTED = 'texted'       # Text recognized, complete


class TaskStatus(str, Enum):
    """Status values for background tasks."""
    
    PENDING = 'pending'     # Task created, waiting to start
    RUNNING = 'running'     # Task is executing
    COMPLETED = 'completed' # Task finished successfully
    FAILED = 'failed'       # Task failed with error
