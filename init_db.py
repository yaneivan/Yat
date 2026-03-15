"""
Initialize database and migrate existing data from JSON to SQLite.

Run this script to:
1. Create database tables
2. Migrate existing projects from data/projects/ to database
3. Migrate existing annotations from data/annotations/ to database
"""

import os
import sys
import json
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from database.session import init_db, engine, Base
from database.models import Project, Image, Annotation, Task
from database.enums import ImageStatus, TaskStatus
from sqlalchemy.orm import Session
from sqlalchemy import select


def migrate_projects():
    """Migrate projects from JSON files to database."""
    from storage import PROJECTS_FOLDER
    
    print("Migrating projects...")
    
    if not os.path.exists(PROJECTS_FOLDER):
        print(f"  Projects folder not found: {PROJECTS_FOLDER}")
        return
    
    session = Session()
    migrated = 0
    
    for project_name in os.listdir(PROJECTS_FOLDER):
        project_path = os.path.join(PROJECTS_FOLDER, project_name)
        if not os.path.isdir(project_path):
            continue
        
        project_json = os.path.join(project_path, 'project.json')
        if not os.path.exists(project_json):
            continue
        
        try:
            with open(project_json, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if project already exists
            existing = session.execute(
                select(Project).where(Project.name == project_name)
            ).scalar_one_or_none()
            
            if existing:
                print(f"  Project '{project_name}' already exists, skipping")
                continue
            
            # Create project
            project = Project(
                name=project_name,
                description=data.get('description', '')
            )
            session.add(project)
            session.flush()  # Get project ID
            
            # Migrate images
            images = data.get('images', [])
            for img_data in images:
                filename = img_data if isinstance(img_data, str) else img_data.get('filename', '')
                if not filename:
                    continue
                
                # Check if image already exists
                existing_img = session.execute(
                    select(Image).where(Image.filename == filename)
                ).scalar_one_or_none()
                
                if existing_img:
                    continue
                
                # Create image
                image = Image(
                    project_id=project.id,
                    filename=filename,
                    original_path=os.path.join('data/originals', filename),
                    cropped_path=os.path.join('data/images', filename),
                    status=ImageStatus.CROP.value
                )
                session.add(image)
            
            migrated += 1
            print(f"  Migrated project: {project_name}")
            
        except Exception as e:
            print(f"  Error migrating project '{project_name}': {e}")
    
    session.commit()
    session.close()
    print(f"  Total projects migrated: {migrated}")


def migrate_annotations():
    """Migrate annotations from JSON files to database."""
    from storage import ANNOTATION_FOLDER
    
    print("Migrating annotations...")
    
    if not os.path.exists(ANNOTATION_FOLDER):
        print(f"  Annotation folder not found: {ANNOTATION_FOLDER}")
        return
    
    session = Session()
    migrated = 0
    skipped = 0
    
    for filename in os.listdir(ANNOTATION_FOLDER):
        if not filename.endswith('.json'):
            continue
        
        annotation_path = os.path.join(ANNOTATION_FOLDER, filename)
        image_name = filename[:-5]  # Remove .json
        
        try:
            with open(annotation_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Find image in database
            image = session.execute(
                select(Image).where(Image.filename == image_name)
            ).scalar_one_or_none()
            
            if not image:
                # Create image entry without project
                print(f"  Warning: Image '{image_name}' not found, creating standalone entry")
                image = Image(
                    project_id=None,
                    filename=image_name,
                    original_path=os.path.join('data/originals', image_name),
                    cropped_path=os.path.join('data/images', image_name),
                    status=data.get('status', ImageStatus.CROP.value)
                )
                session.add(image)
                session.flush()
            
            # Check if annotation already exists
            existing = session.execute(
                select(Annotation).where(Annotation.image_id == image.id)
            ).scalar_one_or_none()
            
            if existing:
                skipped += 1
                continue
            
            # Convert regions and texts to polygons format
            regions = data.get('regions', [])
            texts = data.get('texts', {})
            polygons = []
            
            for i, region in enumerate(regions):
                polygon = {
                    'points': region,
                    'text': texts.get(str(i), texts.get(i, ''))
                }
                polygons.append(polygon)
            
            # Create annotation
            annotation = Annotation(
                image_id=image.id,
                polygons=polygons
            )
            session.add(annotation)

            # Update image status
            if polygons:
                image.status = ImageStatus.SEGMENT.value
            elif data.get('status') == ImageStatus.CROPPED.value:
                image.status = ImageStatus.CROPPED.value

            migrated += 1
            
        except Exception as e:
            print(f"  Error migrating annotation '{filename}': {e}")
    
    session.commit()
    session.close()
    print(f"  Total annotations migrated: {migrated}, skipped: {skipped}")


def main():
    """Main migration function."""
    print("=" * 50)
    print("Database Initialization and Migration")
    print("=" * 50)
    
    # Create tables
    print("\nCreating database tables...")
    init_db()
    print("  Tables created successfully")
    
    # Migrate data
    print("\nMigrating existing data...")
    migrate_projects()
    migrate_annotations()
    
    print("\n" + "=" * 50)
    print("Migration completed!")
    print("=" * 50)


if __name__ == '__main__':
    main()
