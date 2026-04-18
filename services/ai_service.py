"""
AI Service for text detection and recognition.

Provides centralized access to AI models (YOLOv9, TROCR)
with lazy initialization and model caching.
"""

import os
import logging
import threading
from typing import Dict, List, Any, Optional, Callable

import config

# Import AI dependencies
try:
    import torch
    from ultralytics import YOLO

    YOLO_AVAILABLE = True
except ImportError:
    YOLO_AVAILABLE = False

try:
    from transformers import TrOCRProcessor, VisionEncoderDecoderModel
    from PIL import Image

    TROCR_AVAILABLE = True
except ImportError:
    TROCR_AVAILABLE = False
    Image = None

logger = logging.getLogger(__name__)


class AIService:
    """
    Service for AI operations.

    Features:
    - Lazy model initialization
    - Model caching
    - Thread-safe model loading
    - Text line detection (YOLOv9)
    - Text recognition (TROCR)
    """

    def __init__(self):
        self._yolo_model = None
        self._trocr_model = None
        self._trocr_processor = None
        self._device = None
        self._models_initialized = False
        # Блокировка для защиты инициализации моделей
        self._yolo_init_lock = threading.Lock()
        self._trocr_init_lock = threading.Lock()

    def _get_device(self):
        """Get configured device."""
        if self._device is None:
            self._device = torch.device(config.DEVICE)
        return self._device

    def _get_yolo_model(self) -> Optional[YOLO]:
        """
        Get or load YOLO model.
        Thread-safe lazy initialization.

        Returns:
            YOLO model or None if not available
        """
        if not YOLO_AVAILABLE:
            return None

        # Double-checked locking pattern
        if self._yolo_model is None:
            with self._yolo_init_lock:
                # Проверить снова внутри блокировки
                if self._yolo_model is None:
                    # Get model path from config
                    model_path = config.MODEL_PATHS.get(
                        "yolo", "./models/yolo_model.pt"
                    )

                    if not os.path.exists(model_path):
                        raise FileNotFoundError(
                            f"YOLOv9 model not found at {model_path}. "
                            "Please ensure the model file exists."
                        )

                    self._yolo_model = YOLO(model_path)
                    self._yolo_model.to(self._get_device())

        return self._yolo_model

    def _initialize_trocr(self, model_name: str = None):
        """Initialize TROCR model and processor."""
        if not TROCR_AVAILABLE:
            raise Exception(
                "Transformers not available. "
                "Install transformers to enable text recognition."
            )

        # Get model name from config if not specified
        if model_name is None:
            model_name = config.MODEL_PATHS.get("trocr", "raxtemur/trocr-base-ru")

        cache_dir = "./models"

        self._trocr_processor = TrOCRProcessor.from_pretrained(
            model_name, cache_dir=cache_dir
        )
        self._trocr_model = VisionEncoderDecoderModel.from_pretrained(
            model_name, cache_dir=cache_dir
        )
        self._trocr_model.to(self._get_device())
        self._models_initialized = True

    def _get_trocr_model(self):
        """
        Get or load TROCR model.
        Thread-safe lazy initialization.

        Returns:
            Tuple of (model, processor) or (None, None) if not available
        """
        if not TROCR_AVAILABLE:
            return None, None

        # Double-checked locking pattern
        if self._trocr_model is None or self._trocr_processor is None:
            with self._trocr_init_lock:
                # Проверить снова внутри блокировки
                if self._trocr_model is None or self._trocr_processor is None:
                    self._initialize_trocr()

        return self._trocr_model, self._trocr_processor

    def is_yolo_available(self) -> bool:
        """Check if YOLO is available."""
        return YOLO_AVAILABLE and self._get_yolo_model() is not None

    def is_trocr_available(self) -> bool:
        """Check if TROCR is available."""
        return TROCR_AVAILABLE

    def detect_lines(
        self, filename: str, settings: Dict[str, Any] = None, project_id: int = None
    ) -> List[Dict[str, Any]]:
        """
        Detect text lines in an image using YOLOv9.

        Args:
            filename: Image filename
            settings: Detection settings (threshold, simplification, merge)
            project_id: Project ID for project-specific file paths

        Returns:
            List of regions (polygons)
        """
        if settings is None:
            settings = {}

        if not YOLO_AVAILABLE:
            raise Exception("YOLOv9 not available. Install ultralytics and torch.")

        model = self._get_yolo_model()

        if model is None:
            raise Exception("YOLO model not loaded")

        from services.image_storage_service import image_storage_service

        image_path = image_storage_service.get_image_path(filename, project_id)

        if not os.path.exists(image_path):
            raise Exception(f"Image file does not exist: {image_path}")

        # Get settings
        confidence_threshold = settings.get("threshold", 50) / 100.0
        simplification_threshold = settings.get("simplification", 2.0)
        merge_overlapping = settings.get("mergeOverlapping", False)
        overlap_threshold = settings.get("overlapThreshold", 30)

        # Run inference
        results = model(image_path, conf=confidence_threshold)

        # Process results
        regions = []

        for result in results:
            if result.masks is not None:
                # Process segmentation masks
                masks = result.masks.xy
                for mask in masks:
                    points = [{"x": int(p[0]), "y": int(p[1])} for p in mask]

                    # Apply simplification
                    if simplification_threshold > 0:
                        from logic import simplify_points

                        points = simplify_points(points, simplification_threshold)

                    if len(points) >= 3:
                        regions.append({"points": points})

            elif result.boxes is not None:
                # Fallback to bounding boxes
                boxes = result.boxes.xyxy.cpu().numpy()
                for box in boxes:
                    x1, y1, x2, y2 = map(int, box)
                    points = [
                        {"x": x1, "y": y1},
                        {"x": x2, "y": y1},
                        {"x": x2, "y": y2},
                        {"x": x1, "y": y2},
                    ]

                    if simplification_threshold > 0:
                        from logic import simplify_points

                        points = simplify_points(points, simplification_threshold)

                    regions.append({"points": points})

        # Optionally merge overlapping regions
        if merge_overlapping:
            from logic import merge_overlapping_regions, remove_duplicate_regions

            # First remove duplicates (small segments inside large ones)
            regions = remove_duplicate_regions(regions, containment_threshold=0.9)

            # Then merge overlapping regions on the same line
            regions = merge_overlapping_regions(regions, overlap_threshold)

        return regions

    def recognize_text_in_region(
        self, image: Any, bbox: tuple, padding: int = 10
    ) -> str:
        """
        Recognize text in a specific region.

        Args:
            image: PIL Image object
            bbox: Bounding box (left, top, right, bottom)
            padding: Padding around the region

        Returns:
            Recognized text
        """
        if not TROCR_AVAILABLE:
            return ""

        model, processor = self._get_trocr_model()

        if model is None or processor is None:
            return ""

        # Extract region with padding
        left, top, right, bottom = bbox
        left = max(0, left - padding)
        top = max(0, top - padding)
        right = min(image.width, right + padding)
        bottom = min(image.height, bottom + padding)

        cropped_image = image.crop((left, top, right, bottom))

        # Preprocess
        pixel_values = processor(cropped_image, return_tensors="pt").pixel_values
        pixel_values = pixel_values.to(self._get_device())

        # Generate text
        generated_ids = model.generate(pixel_values)
        text = processor.batch_decode(generated_ids, skip_special_tokens=True)[0]

        return text

    def recognize_text(
        self,
        filename: str,
        regions: List[Dict[str, Any]] = None,
        progress_callback: Callable = None,
        project_id: int = None,
        user_id: int = None,
    ) -> Dict[int, str]:
        """
        Recognize text in image regions using TROCR.

        Args:
            filename: Image filename
            regions: List of regions to process (or None for all)
            progress_callback: Optional callback(current, total)
            project_id: Optional project ID to scope annotation lookup

        Returns:
            Dictionary of region_index -> recognized_text
        """
        if not TROCR_AVAILABLE:
            raise Exception("Transformers not available.")

        from services.image_service import image_service
        from services.annotation_service import annotation_service
        from database.enums import ImageStatus

        msg = f"[recognize_text] START: filename={filename}, regions={len(regions) if regions else 0}, project_id={project_id}, user_id={user_id}"
        logger.info(msg)

        image = image_service.get_image(filename, project_id)

        if image is None:
            raise Exception(f"Image not found: {filename}")

        image = image.convert("RGB")

        annotation_data = annotation_service.get_annotation(filename, project_id)

        if regions is None:
            regions = annotation_data.get("regions", [])

        logger.info(f"[recognize_text] regions count: {len(regions)}")

        recognized_texts = {}
        total_regions = len(regions)

        for idx, region in enumerate(regions):
            try:
                xs = [p["x"] for p in region["points"]]
                ys = [p["y"] for p in region["points"]]
                bbox = (min(xs), min(ys), max(xs), max(ys))

                text = self.recognize_text_in_region(image, bbox)
                recognized_texts[idx] = text
                logger.info(f"[recognize_text] Region {idx} done, text len={len(text)}")

                if progress_callback:
                    progress_callback(idx + 1, total_regions)

            except Exception as e:
                logger.error(f"Error processing region {idx}: {e}", exc_info=True)
                recognized_texts[idx] = ""

        annotation_data["texts"] = recognized_texts
        annotation_data["status"] = ImageStatus.RECOGNIZED.value
        annotation_data["image_name"] = filename

        can_save = True
        if user_id and project_id:
            from services.permission_service import permission_service

            proj_role = permission_service.get_project_role(user_id, project_id)
            print(
                f"[recognize_text] user_id={user_id}, project_id={project_id}, role={proj_role}"
            )
            if proj_role == "viewer":
                can_save = False

        if can_save:
            logger.info(f"[recognize_text] Saving annotation for {filename}")
            annotation_service.save_annotation(filename, annotation_data, project_id)
        else:
            logger.info(
                f"[recognize_text] Text recognized but NOT saved (read-only): {filename}"
            )

        logger.info("[recognize_text] COMPLETED")
        return recognized_texts

    def initialize_models(self, trocr_model_name: str = "raxtemur/trocr-base-ru"):
        """
        Pre-initialize all AI models.

        Args:
            trocr_model_name: TROCR model name to load
        """
        # Initialize YOLO
        if YOLO_AVAILABLE:
            try:
                self._get_yolo_model()
                logger.info("YOLO model initialized")
            except Exception as e:
                logger.error(f"Failed to initialize YOLO: {e}")

        # Initialize TROCR
        if TROCR_AVAILABLE:
            try:
                self._initialize_trocr(trocr_model_name)
                logger.info(f"TROCR model initialized on {self._get_device()}")
            except Exception as e:
                logger.error(f"Failed to initialize TROCR: {e}")


# Global AI service instance
ai_service = AIService()
