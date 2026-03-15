"""
Test script for PDF export functionality.

This script tests the PDF export service without running the Flask server.
It generates PDF files for all variants and saves them to the output directory.

Usage:
    uv run test_pdf_export.py [project_name]
    
If project_name is not specified, uses the first available project.
"""

import os
import sys
import time
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import services
from services.project_service import project_service
from services.pdf_export_service import pdf_export_service


def get_test_project():
    """Get a project for testing."""
    projects = project_service.get_all_projects()
    
    if not projects:
        print("❌ No projects found in database")
        print("\nPlease create a project first:")
        print("1. Run the Flask app: uv run python app.py")
        print("2. Create a project via web interface")
        print("3. Add some images with annotations")
        return None
    
    print(f"Found {len(projects)} project(s):")
    for i, proj in enumerate(projects):
        img_count = len(proj.get('images', []))
        print(f"  {i + 1}. {proj['name']} - {img_count} images")
    
    return projects[0]['name']


def test_pdf_export(project_name: str, output_dir: str = "pdf_output"):
    """
    Test all PDF export variants for a project.
    
    Args:
        project_name: Name of the project to export
        output_dir: Directory to save test PDFs
    """
    print(f"\n{'='*60}")
    print(f"Testing PDF export for project: {project_name}")
    print(f"{'='*60}\n")
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Get project info
    project_data = project_service.get_project(project_name)
    if not project_data:
        print(f"❌ Project '{project_name}' not found")
        return
    
    images = project_data.get('images', [])
    print(f"Project contains {len(images)} image(s)\n")
    
    # List images with their annotation status
    from services.annotation_service import annotation_service
    
    for img in images:
        filename = img['filename']
        annotation = annotation_service.get_annotation(filename)
        regions_count = len(annotation.get('regions', []))
        texts_count = len([t for t in annotation.get('texts', {}).values() if t and t.strip()])
        print(f"  📄 {filename}: {regions_count} polygons, {texts_count} text blocks")
    
    print()
    
    # Test variants
    variants = [
        ('original', 'Оригинал (только изображения)'),
        ('overlay', 'Полигоны (изображения + разметка)'),
        ('parallel', 'Параллельный (изображение + текст)'),
        ('text', 'Текст (чистый текст)'),
    ]
    
    results = []
    
    for variant_name, variant_desc in variants:
        print(f"⏳ Генерация варианта: {variant_desc}...")
        start_time = time.time()
        
        try:
            pdf_bytes = pdf_export_service.export_project(
                project_name=project_name,
                variant=variant_name
            )
            
            elapsed = time.time() - start_time
            
            if pdf_bytes:
                filename = f"{project_name}_{variant_name}.pdf"
                filepath = output_path / filename
                
                with open(filepath, 'wb') as f:
                    f.write(pdf_bytes)
                
                size_kb = len(pdf_bytes) / 1024
                print(f"✅ Успешно! Сохранено в {filepath} ({size_kb:.1f} KB, {elapsed:.2f}s)\n")
                results.append((variant_name, True, elapsed, size_kb))
            else:
                print(f"❌ Ошибка: export_project вернул None ({elapsed:.2f}s)\n")
                results.append((variant_name, False, elapsed, 0))
                
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ Исключение: {e} ({elapsed:.2f}s)\n")
            import traceback
            traceback.print_exc()
            results.append((variant_name, False, elapsed, 0))
    
    # Summary
    print(f"\n{'='*60}")
    print("РЕЗУЛЬТАТЫ ТЕСТА")
    print(f"{'='*60}")
    
    success_count = sum(1 for _, success, _, _ in results if success)
    
    for variant_name, success, elapsed, size_kb in results:
        status = "✅" if success else "❌"
        size_str = f"{size_kb:.1f} KB" if success else "N/A"
        print(f"  {status} {variant_name:12} - {elapsed:.2f}s, {size_str}")
    
    print(f"\nИтого: {success_count}/{len(variants)} вариантов успешно")
    print(f"Файлы сохранены в: {output_path.absolute()}")
    
    return success_count == len(variants)


def main():
    """Main entry point."""
    print("="*60)
    print("HTR Polygon Annotation Tool - PDF Export Test")
    print("="*60)
    
    # Get project name from command line or use first available
    if len(sys.argv) > 1:
        project_name = sys.argv[1]
    else:
        project_name = get_test_project()
        if not project_name:
            sys.exit(1)
    
    # Run test
    success = test_pdf_export(project_name)
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
