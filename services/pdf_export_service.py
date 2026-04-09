"""
PDF Export Service for generating PDF documents from annotated images.

Provides 4 export variants:
1. original - Images only, no annotations
2. overlay - Images with polygon overlays
3. parallel - Side-by-side: image with polygons + text blocks
4. text - Text blocks only (clean text for copying)

Uses reportlab for PDF generation with Cyrillic font support.
"""

import io
import os
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image as PILImage

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.platypus.flowables import Flowable
from reportlab.platypus import Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

# Import services
from services.project_service import project_service
from services.image_storage_service import image_storage_service
from services.annotation_service import annotation_service


# =============================================================================
# Font configuration for Cyrillic support
# =============================================================================

def get_cyrillic_font_path() -> Optional[str]:
    """
    Find a suitable Cyrillic font on the system.
    Returns path to font file or None if not found.
    """
    # Common Cyrillic-compatible fonts
    font_candidates = [
        # Windows fonts
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        # Linux fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        # macOS fonts
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
    ]
    
    for font_path in font_candidates:
        if os.path.exists(font_path):
            return font_path
    
    # Try to find any .ttf font in system fonts
    import glob
    for pattern in [r"C:\Windows\Fonts\*.ttf", "/usr/share/fonts/**/*.ttf"]:
        fonts = glob.glob(pattern, recursive=True)
        if fonts:
            return fonts[0]
    
    return None


def register_cyrillic_font() -> str:
    """
    Register a Cyrillic font with reportlab.
    Returns the font name to use.
    """
    font_path = get_cyrillic_font_path()
    
    if font_path:
        try:
            pdfmetrics.registerFont(TTFont('CyrillicFont', font_path))
            return 'CyrillicFont'
        except Exception as e:
            print(f"Warning: Could not register font {font_path}: {e}")
    
    # Fallback to built-in font (limited Cyrillic support)
    return 'Helvetica'


# =============================================================================
# Custom Flowable for drawing images with polygon overlays
# =============================================================================

class ImageWithPolygons(Flowable):
    """
    Custom Flowable that draws an image with polygon overlays.
    Shows text inside polygons (like the editor).
    """

    def __init__(
        self,
        image_path: str,
        polygons: List[Dict[str, Any]],
        texts: Dict[str, str],
        max_width: float,
        max_height: float,
        show_text: bool = True,
        polygon_color: Tuple[float, float, float] = (1.0, 0.0, 0.0),  # Red
        line_width: float = 2,
        font_name: str = 'Helvetica'
    ):
        super().__init__()
        self.image_path = image_path
        self.polygons = polygons
        self.texts = texts
        self.max_width = max_width
        self.max_height = max_height
        self.show_text = show_text
        self.polygon_color = polygon_color
        self.line_width = line_width
        self.font_name = font_name

        # Calculate dimensions
        try:
            with PILImage.open(image_path) as img:
                self.img_width, self.img_height = img.size
        except:
            self.img_width, self.img_height = 100, 100

        # Scale to fit
        scale = min(max_width / self.img_width, max_height / self.img_height)
        self.draw_width = self.img_width * scale
        self.draw_height = self.img_height * scale

    def wrap(self, availWidth, availHeight):
        return (self.draw_width, self.draw_height)

    def draw(self, canvas_obj=None):
        if canvas_obj is None:
            canvas_obj = self.canv

        # Save state
        canvas_obj.saveState()

        # Draw image
        try:
            canvas_obj.drawImage(
                self.image_path,
                0, 0,
                self.draw_width,
                self.draw_height,
                preserveAspectRatio=False
            )
        except Exception as e:
            print(f"Error drawing image: {e}")
            # Draw placeholder
            canvas_obj.setFillColor(colors.lightgrey)
            canvas_obj.rect(0, 0, self.draw_width, self.draw_height, fill=1)
            canvas_obj.setFillColor(colors.black)
            canvas_obj.drawString(10, self.draw_height/2, "Image not found")

        # Draw polygons
        scale_x = self.draw_width / self.img_width
        scale_y = self.draw_height / self.img_height

        for i, polygon in enumerate(self.polygons):
            points = polygon.get('points', [])
            if len(points) < 3:
                continue

            # Convert points to canvas coordinates
            canvas_points = []
            for p in points:
                x = p['x'] * scale_x
                y = self.draw_height - (p['y'] * scale_y)  # Flip Y axis
                canvas_points.append((x, y))

            # Draw polygon outline
            canvas_obj.setStrokeColor(colors.Color(*self.polygon_color))
            canvas_obj.setLineWidth(self.line_width)
            canvas_obj.setFillColor(colors.Color(*self.polygon_color, alpha=0.2))

            path = canvas_obj.beginPath()
            path.moveTo(*canvas_points[0])
            for x, y in canvas_points[1:]:
                path.lineTo(x, y)
            path.close()
            canvas_obj.drawPath(path, fill=1, stroke=1)

            # Draw text inside polygon (if available)
            if self.show_text:
                text = self.texts.get(str(i), '').strip()
                if text:
                    # Calculate centroid
                    cx = sum(p[0] for p in canvas_points) / len(canvas_points)
                    cy = sum(p[1] for p in canvas_points) / len(canvas_points)

                    # Calculate polygon width for text sizing
                    min_x = min(p[0] for p in canvas_points)
                    max_x = max(p[0] for p in canvas_points)
                    polygon_width = max_x - min_x

                    # Font size based on polygon size - smaller for better fit
                    font_size = max(6, min(14, int(polygon_width * 0.08)))

                    # Truncate text if too long
                    max_chars = max(5, int(polygon_width / 10))
                    if len(text) > max_chars:
                        text = text[:max_chars-3] + '...'

                    # Draw text with yellow background (like editor)
                    # Use registered Cyrillic font
                    canvas_obj.setFont(self.font_name, font_size)
                    text_width = canvas_obj.stringWidth(text, self.font_name, font_size)
                    text_height = font_size * 1.2

                    # Background rectangle (yellow, semi-transparent look)
                    bg_padding = 2
                    canvas_obj.setFillColor(colors.Color(1, 1, 0, 0.6))  # Yellow
                    canvas_obj.setStrokeColor(colors.black)
                    canvas_obj.setLineWidth(0.5)
                    canvas_obj.roundRect(
                        cx - text_width/2 - bg_padding,
                        cy - text_height/2 - bg_padding,
                        text_width + bg_padding*2,
                        text_height + bg_padding*2,
                        3,  # rounded corners
                        fill=1,
                        stroke=1
                    )

                    # Black bold text with Cyrillic support
                    canvas_obj.setFillColor(colors.black)
                    # Try to draw text - reportlab should handle Unicode with registered font
                    try:
                        # Use drawString with the registered Cyrillic font
                        canvas_obj.drawString(
                            cx - text_width/2,
                            cy - font_size/2,
                            text
                        )
                    except Exception as e:
                        # Fallback: try to encode as latin-1 and draw
                        try:
                            # Try to transliterate or use fallback text
                            fallback_text = text.encode('utf-8', errors='replace').decode('utf-8')
                            canvas_obj.drawString(
                                cx - text_width/2,
                                cy - font_size/2,
                                fallback_text
                            )
                        except:
                            # Last resort: draw placeholder
                            canvas_obj.drawString(
                                cx - text_width/2,
                                cy - font_size/2,
                                '[text]'
                            )

        # Restore state
        canvas_obj.restoreState()


class TextBlocks(Flowable):
    """
    Custom Flowable that draws text blocks with numbers.
    """
    
    def __init__(
        self,
        texts: Dict[str, str],
        max_width: float,
        font_name: str = 'Helvetica',
        font_size: int = 11,
        line_spacing: float = 1.5
    ):
        super().__init__()
        self.texts = texts
        self.max_width = max_width
        self.font_name = font_name
        self.font_size = font_size
        self.line_spacing = line_spacing
        
        # Calculate height needed
        self.lines = []
        for i, text in sorted(texts.items(), key=lambda x: int(x[0])):
            if text:
                self.lines.append((int(i) + 1, text.strip()))
        
        # Estimate height
        self.estimated_height = len(self.lines) * font_size * line_spacing * 2 + 20
    
    def wrap(self, availWidth, availHeight):
        return (self.max_width, min(self.estimated_height, availHeight))
    
    def draw(self, canvas_obj=None):
        if canvas_obj is None:
            canvas_obj = self.canv
        
        canvas_obj.saveState()
        canvas_obj.setFont(self.font_name, self.font_size)
        
        y = self.estimated_height - 10
        line_height = self.font_size * self.line_spacing
        
        for num, text in self.lines:
            if y < 10:
                break
            
            # Draw number badge
            canvas_obj.setFillColor(colors.Color(0, 0.5, 1))
            canvas_obj.roundRect(0, y - self.font_size + 2, 18, self.font_size + 2, 3, fill=1)
            
            canvas_obj.setFillColor(colors.white)
            canvas_obj.drawString(3, y, str(num))
            
            # Draw text
            canvas_obj.setFillColor(colors.black)
            canvas_obj.drawString(25, y, text[:80])  # Truncate long lines
            
            y -= line_height
        
        canvas_obj.restoreState()


# =============================================================================
# PDF Export Service
# =============================================================================

class PDFExportService:
    """
    Service for exporting annotated images to PDF.
    
    Supports 4 variants:
    1. original - Images only
    2. overlay - Images with polygon overlays
    3. parallel - Side-by-side: image + text
    4. text - Text blocks only
    """
    
    def __init__(self):
        self.font_name = register_cyrillic_font()
        self.styles = getSampleStyleSheet()
        self._setup_styles()
    
    def _setup_styles(self):
        """Configure paragraph styles for Cyrillic text."""
        self.styles.add(ParagraphStyle(
            name='CyrillicNormal',
            parent=self.styles['Normal'],
            fontName=self.font_name,
            fontSize=11,
            leading=14,
            encoding='utf-8'
        ))
        
        self.styles.add(ParagraphStyle(
            name='CyrillicHeading',
            parent=self.styles['Heading1'],
            fontName=self.font_name,
            fontSize=14,
            leading=18,
            encoding='utf-8'
        ))
    
    def export_original(
        self,
        project_name: str,
        output: io.BytesIO,
        page_size: Tuple[float, float] = A4
    ) -> bool:
        """
        Export project to PDF with images only (no annotations).
        
        Args:
            project_name: Project name
            output: BytesIO output stream
            page_size: PDF page size (default: A4)

        Returns:
            True if successful, False otherwise
        """
        try:
            doc = SimpleDocTemplate(
                output,
                pagesize=page_size,
                rightMargin=10*mm,
                leftMargin=10*mm,
                topMargin=10*mm,
                bottomMargin=10*mm
            )

            images = project_service.get_images(project_name)
            if not images:
                return False

            story = []
            page_width, page_height = page_size
            max_img_width = page_width - 40*mm
            max_img_height = page_height - 40*mm

            for img_idx, img_data in enumerate(images):
                filename = img_data['filename']
                image_path = image_storage_service.get_image_path(filename, project_name)

                if not os.path.exists(image_path):
                    continue

                # Add title
                story.append(Paragraph(
                    f"<b>{filename}</b>",
                    self.styles['CyrillicHeading']
                ))
                story.append(Spacer(1, 3*mm))

                # Add image
                img_flowable = RLImage(
                    image_path,
                    width=max_img_width,
                    height=max_img_height,
                    kind='proportional'
                )
                story.append(img_flowable)
                
                # Page break after each image (except last)
                if img_idx < len(images) - 1:
                    story.append(PageBreak())

            doc.build(story)
            return True

        except Exception as e:
            print(f"PDFExportService.export_original error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def export_overlay(
        self,
        project_name: str,
        output: io.BytesIO,
        page_size: Tuple[float, float] = A4,
        show_text: bool = True,
        polygon_color: Tuple[float, float, float] = (1.0, 0.0, 0.0)
    ) -> bool:
        """
        Export project to PDF with images and polygon overlays.
        
        Args:
            project_name: Project name
            output: BytesIO output stream
            page_size: PDF page size
            show_text: Show text inside polygons (like editor)
            polygon_color: RGB color for polygons (0-1 range)

        Returns:
            True if successful, False otherwise
        """
        try:
            doc = SimpleDocTemplate(
                output,
                pagesize=page_size,
                rightMargin=10*mm,
                leftMargin=10*mm,
                topMargin=10*mm,
                bottomMargin=10*mm
            )

            images = project_service.get_images(project_name)
            if not images:
                return False

            story = []
            page_width, page_height = page_size
            max_img_width = page_width - 40*mm
            max_img_height = page_height - 40*mm

            for img_idx, img_data in enumerate(images):
                filename = img_data['filename']
                image_path = image_storage_service.get_image_path(filename, project_name)

                if not os.path.exists(image_path):
                    continue

                # Get annotation with project scope
                annotation = annotation_service.get_annotation(filename, project_name)
                polygons = annotation.get('regions', [])
                texts = annotation.get('texts', {})

                # Create title
                title = Paragraph(
                    f"<b>{filename}</b>",
                    self.styles['CyrillicHeading']
                )

                # Create image with polygons
                if polygons:
                    img_flowable = ImageWithPolygons(
                        image_path,
                        polygons,
                        texts,
                        max_img_width,
                        max_img_height,
                        show_text=show_text,
                        polygon_color=polygon_color,
                        font_name=self.font_name
                    )
                else:
                    img_flowable = RLImage(
                        image_path,
                        width=max_img_width,
                        height=max_img_height,
                        kind='proportional'
                    )

                # Wrap title + image in KeepTogether to prevent splitting
                story.append(KeepTogether([title, Spacer(1, 3*mm), img_flowable]))
                
                # Add space between images (only if not last)
                if img_idx < len(images) - 1:
                    story.append(Spacer(1, 10*mm))
                    story.append(PageBreak())

            doc.build(story)
            return True

        except Exception as e:
            print(f"PDFExportService.export_overlay error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def export_parallel(
        self,
        project_name: str,
        output: io.BytesIO,
        page_size: Tuple[float, float] = landscape(A4),
        show_text_on_image: bool = True
    ) -> bool:
        """
        Export project to PDF with side-by-side layout:
        Left: Original image (no overlay)
        Right: Image with polygon text overlay (like editor)

        Each image gets its own page in landscape orientation.

        Args:
            project_name: Project name
            output: BytesIO output stream
            page_size: PDF page size (default: landscape A4)
            show_text_on_image: Show text inside polygons on right image

        Returns:
            True if successful, False otherwise
        """
        try:
            doc = SimpleDocTemplate(
                output,
                pagesize=page_size,
                rightMargin=10*mm,
                leftMargin=10*mm,
                topMargin=10*mm,
                bottomMargin=10*mm,
                allowSplitting=True
            )

            images = project_service.get_images(project_name)
            if not images:
                return False

            story = []
            page_width, page_height = page_size

            # Split page: 50% left (original), 50% right (overlay)
            content_width = (page_width - 50*mm) * 0.5
            max_img_height = page_height - 30*mm

            for img_idx, img_data in enumerate(images):
                filename = img_data['filename']
                image_path = image_storage_service.get_image_path(filename, project_name)

                if not os.path.exists(image_path):
                    continue

                # Get annotation with project scope
                annotation = annotation_service.get_annotation(filename, project_name)
                polygons = annotation.get('regions', [])
                texts = annotation.get('texts', {})

                # Add title centered
                story.append(Paragraph(
                    f"<b>{filename}</b>",
                    self.styles['CyrillicHeading']
                ))
                story.append(Spacer(1, 3*mm))

                # Left: Original image (no overlay)
                original_img = RLImage(
                    image_path,
                    width=content_width,
                    height=max_img_height,
                    kind='proportional'
                )

                # Right: Image with polygons and text overlay
                if polygons:
                    overlay_img = ImageWithPolygons(
                        image_path,
                        polygons,
                        texts,
                        content_width,
                        max_img_height,
                        show_text=show_text_on_image,
                        font_name=self.font_name
                    )
                else:
                    overlay_img = RLImage(
                        image_path,
                        width=content_width,
                        height=max_img_height,
                        kind='proportional'
                    )

                # Create side-by-side table
                table = Table([[original_img, overlay_img]], colWidths=[content_width, content_width])
                table.setStyle(TableStyle([
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ALIGN', (0, 0), (0, -1), 'CENTER'),
                    ('ALIGN', (1, 0), (1, -1), 'CENTER'),
                ]))

                story.append(table)

                # Page break after each image (except last)
                if img_idx < len(images) - 1:
                    story.append(PageBreak())

            doc.build(story)
            return True

        except Exception as e:
            print(f"PDFExportService.export_parallel error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def export_text(
        self,
        project_name: str,
        output: io.BytesIO,
        page_size: Tuple[float, float] = A4
    ) -> bool:
        """
        Export project to PDF with text blocks only (clean text for copying).
        
        Args:
            project_name: Project name
            output: BytesIO output stream
            page_size: PDF page size
        
        Returns:
            True if successful, False otherwise
        """
        try:
            doc = SimpleDocTemplate(
                output,
                pagesize=page_size,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=20*mm,
                bottomMargin=20*mm
            )
            
            images = project_service.get_images(project_name)
            if not images:
                return False
            
            story = []
            
            for img_data in images:
                filename = img_data['filename']

                # Get annotation
                annotation = annotation_service.get_annotation(filename, project_name)
                texts = annotation.get('texts', {})
                
                # Add title
                story.append(Paragraph(
                    f"<b>{filename}</b>",
                    self.styles['CyrillicHeading']
                ))
                story.append(Spacer(1, 5*mm))
                
                # Add text blocks
                has_text = False
                for i, text in sorted(texts.items(), key=lambda x: int(x[0])):
                    if text and text.strip():
                        has_text = True
                        story.append(Paragraph(
                            f"<b>{int(i)+1}:</b> {self._escape_xml(text.strip())}",
                            self.styles['CyrillicNormal']
                        ))
                        story.append(Spacer(1, 3*mm))
                
                if not has_text:
                    story.append(Paragraph(
                        "<i>(нет распознанного текста)</i>",
                        self.styles['CyrillicNormal']
                    ))
                
                story.append(Spacer(1, 15*mm))
            
            doc.build(story)
            return True
            
        except Exception as e:
            print(f"PDFExportService.export_text error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _escape_xml(self, text: str) -> str:
        """Escape special XML characters in text."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;')
        )
    
    def export_project(
        self,
        project_name: str,
        variant: str = 'overlay',
        page_size: Tuple[float, float] = None
    ) -> Optional[bytes]:
        """
        Export project to PDF with specified variant.
        
        Args:
            project_name: Project name
            variant: Export variant ('original', 'overlay', 'parallel', 'text')
            page_size: Optional custom page size
        
        Returns:
            PDF bytes or None if failed
        """
        output = io.BytesIO()
        
        # Select export method
        export_methods = {
            'original': self.export_original,
            'overlay': self.export_overlay,
            'parallel': self.export_parallel,
            'text': self.export_text
        }
        
        if variant not in export_methods:
            print(f"Unknown variant: {variant}")
            return None
        
        method = export_methods[variant]
        
        # Set default page sizes
        if page_size is None:
            if variant == 'parallel':
                page_size = landscape(A4)
            else:
                page_size = A4
        
        success = method(project_name, output, page_size)
        
        if success:
            output.seek(0)
            return output.getvalue()
        
        return None


# Global PDF export service instance
pdf_export_service = PDFExportService()
