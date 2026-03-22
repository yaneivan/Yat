"""SQLAlchemy ORM models."""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from database.session import Base
from database.enums import ImageStatus, TaskStatus


class Project(Base):
    """Project model - groups images together."""
    
    __tablename__ = 'projects'
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    description = Column(Text, default='')
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    images = relationship('Image', back_populates='project', cascade='all, delete-orphan')
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'image_count': len(self.images),
        }


class Image(Base):
    """Image model - represents a cropped image in a project."""

    __tablename__ = 'images'

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='CASCADE'), nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    original_path = Column(String(512))  # Path to original (backup)
    cropped_path = Column(String(512))   # Path to cropped image
    status = Column(String(50), default=ImageStatus.CROP.value)  # ImageStatus: crop, cropped, segment, texted, review_pending, reviewed
    crop_params = Column(JSON)  # {x, y, width, height, angle}
    comment = Column(Text, default='')  # Comment from reviewer
    reviewed_at = Column(DateTime)  # Timestamp of review
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship('Project', back_populates='images')
    annotations = relationship('Annotation', back_populates='image', cascade='all, delete-orphan')

    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'project_id': self.project_id,
            'filename': self.filename,
            'original_path': self.original_path,
            'cropped_path': self.cropped_path,
            'status': self.status,
            'crop_params': self.crop_params,
            'comment': self.comment,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Annotation(Base):
    """Annotation model - polygons and recognized text for an image."""
    
    __tablename__ = 'annotations'
    
    id = Column(Integer, primary_key=True, index=True)
    image_id = Column(Integer, ForeignKey('images.id', ondelete='CASCADE'), nullable=False, index=True, unique=True)
    polygons = Column(JSON, default=list)  # [{points: [[x1,y1], ...], text: '', confidence: 0.0}]
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    image = relationship('Image', back_populates='annotations')
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'image_id': self.image_id,
            'polygons': self.polygons,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class Task(Base):
    """Task model - background job tracking."""
    
    __tablename__ = 'tasks'
    
    id = Column(String(64), primary_key=True)  # UUID string
    type = Column(String(50), nullable=False)  # 'detect', 'recognize'
    project_id = Column(Integer, ForeignKey('projects.id', ondelete='SET NULL'), index=True)
    status = Column(String(20), default=TaskStatus.PENDING.value, index=True)  # TaskStatus: pending, running, completed, failed
    progress = Column(Integer, default=0)  # 0-100
    result = Column(JSON, default={})  # {error: '', data: {...}}
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.id,
            'type': self.type,
            'project_id': self.project_id,
            'status': self.status,
            'progress': self.progress,
            'result': self.result,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }
