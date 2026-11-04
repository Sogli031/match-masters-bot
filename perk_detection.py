from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

PERK_NONE = "none"
PERK_UNKNOWN = "unknown"

PERK_STATUS_AVAILABLE = "available"
PERK_STATUS_USED = "used"
PERK_STATUS_UNKNOWN = "unknown"

PERK_TEMPLATE_DIR = Path(__file__).resolve().parent / "assets" / "perks"
PERK_TEMPLATE_THRESHOLD = 0.78

_STATUS_SUFFIXES = {
    PERK_STATUS_AVAILABLE: "_available",
    PERK_STATUS_USED: "_used",
}


@dataclass(frozen=True)
class PerkTemplate:
    perk_key: str
    status: str
    path: Path
    image: Image.Image

    @property
    def name(self):
        return self.path.name


@dataclass(frozen=True)
class PerkSlotDetection:
    slot_number: int
    perk_key: str
    status: str
    score: float
    template_name: str | None = None

    @property
    def available(self):
        return self.status == PERK_STATUS_AVAILABLE and self.perk_key not in {
            PERK_NONE,
            PERK_UNKNOWN,
        }

    def to_debug_payload(self):
        return {
            "slot": self.slot_number,
            "perk": self.perk_key,
            "status": self.status,
            "score": round(float(self.score), 4),
            "template": self.template_name,
        }


def _load_template(path: Path):
    with Image.open(path) as image:
        return image.convert("RGB")


def _parse_template_path(path: Path):
    stem = path.stem
    for status, suffix in _STATUS_SUFFIXES.items():
        if stem.endswith(suffix):
            perk_key = stem[: -len(suffix)]
            if perk_key:
                return perk_key, status
    return None


def load_perk_templates(directory=PERK_TEMPLATE_DIR):
    directory = Path(directory)
    templates = []
    if not directory.exists():
        return templates
    for path in sorted(directory.glob("*.png")):
        parsed = _parse_template_path(path)
        if parsed is None:
            continue
        perk_key, status = parsed
        templates.append(
            PerkTemplate(
                perk_key=perk_key,
                status=status,
                path=path,
                image=_load_template(path),
            )
        )
    return templates


def _as_gray_array(image):
    if not isinstance(image, Image.Image):
        image = Image.fromarray(np.asarray(image))
    rgb = image.convert("RGB")
    return cv2.cvtColor(np.asarray(rgb), cv2.COLOR_RGB2GRAY)


def _as_rgb_image(image):
    if isinstance(image, Image.Image):
        return image.convert("RGB")
    return Image.fromarray(np.asarray(image)).convert("RGB")


def _slot_image_for_template(slot_image, template_image):
    slot = _as_rgb_image(slot_image)
    template = _as_rgb_image(template_image)
    if slot.size == template.size:
        return slot

    slot_width, slot_height = slot.size
    template_width, template_height = template.size
    if slot_width >= template_width and slot_height >= template_height:
        return _crop_centered(
            slot,
            (slot_width / 2, slot_height / 2),
            (template_width, template_height),
        )
    return slot.resize(template.size)


def _template_color_distance(slot_image, template_image):
    slot_rgb = _slot_image_for_template(slot_image, template_image)
    template_rgb = _as_rgb_image(template_image)
    slot_values = np.asarray(slot_rgb, dtype=np.float32)
    template_values = np.asarray(template_rgb, dtype=np.float32)
    return float(np.mean(np.abs(slot_values - template_values)))


def _status_color_signature(image):
    """Describe the colored perk button without depending on pixel alignment."""
    rgb = np.asarray(_as_rgb_image(image), dtype=np.uint8)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    height, width = hsv.shape[:2]
    yy, xx = np.ogrid[:height, :width]
    # Ignore most of the purple panel around the button.  Available perks are
    # strongly saturated blue/yellow; used perks are desaturated gray.
    ellipse = (
        ((xx - (width - 1) / 2) / max(1.0, width * 0.42)) ** 2
        + ((yy - (height - 1) / 2) / max(1.0, height * 0.44)) ** 2
        <= 1.0
    )
    saturation = hsv[:, :, 1][ellipse]
    value = hsv[:, :, 2][ellipse]
    if saturation.size == 0:
        return np.zeros(3, dtype=np.float32)
    return np.array(
        (
            float(saturation.mean()) / 255.0,
            float(np.mean(saturation > 100)),
            float(value.mean()) / 255.0,
        ),
        dtype=np.float32,
    )


def _status_template_for_perk(slot_image, templates):
    best_template = None
    best_distance = None
    for template in templates:
        aligned_slot = _slot_image_for_template(slot_image, template.image)
        distance = float(
            np.linalg.norm(
                _status_color_signature(aligned_slot)
                - _status_color_signature(template.image)
            )
        )
        if best_distance is None or distance < best_distance:
            best_distance = distance
            best_template = template
    return best_template


def _crop_centered(image, center, size):
    center_x, center_y = center
    width, height = size
    left = int(round(center_x - width / 2))
    top = int(round(center_y - height / 2))
    return image.crop((left, top, left + int(width), top + int(height)))


def _template_score(slot_image, template_image):
    slot_gray = _as_gray_array(slot_image)
    template_gray = _as_gray_array(template_image)

    if slot_gray.shape[0] < template_gray.shape[0] or slot_gray.shape[1] < template_gray.shape[1]:
        slot_gray = cv2.resize(
            slot_gray,
            (template_gray.shape[1], template_gray.shape[0]),
            interpolation=cv2.INTER_AREA,
        )
    result = cv2.matchTemplate(slot_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    result = np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)
    return float(result.max())


def detect_perk_slot(slot_image, templates=None, threshold=PERK_TEMPLATE_THRESHOLD, slot_number=1):
    templates = load_perk_templates() if templates is None else list(templates)
    best_template = None
    best_score = 0.0
    for template in templates:
        score = _template_score(slot_image, template.image)
        if score > best_score:
            best_score = score
            best_template = template

    if best_template is None or best_score < threshold:
        return PerkSlotDetection(
            slot_number=slot_number,
            perk_key=PERK_UNKNOWN,
            status=PERK_STATUS_UNKNOWN,
            score=best_score,
            template_name=best_template.name if best_template is not None else None,
        )
    status_template = _status_template_for_perk(
        slot_image,
        [template for template in templates if template.perk_key == best_template.perk_key],
    ) or best_template
    return PerkSlotDetection(
        slot_number=slot_number,
        perk_key=status_template.perk_key,
        status=status_template.status,
        score=best_score,
        template_name=status_template.name,
    )


def detect_perk_slots(image, slot_centers, slot_size, templates=None, threshold=PERK_TEMPLATE_THRESHOLD):
    if not isinstance(image, Image.Image):
        image = Image.fromarray(np.asarray(image)).convert("RGB")
    else:
        image = image.convert("RGB")
    templates = load_perk_templates() if templates is None else list(templates)
    detections = []
    for index, center in enumerate(slot_centers, start=1):
        slot_image = _crop_centered(image, center, slot_size)
        detections.append(
            detect_perk_slot(
                slot_image,
                templates=templates,
                threshold=threshold,
                slot_number=index,
            )
        )
    return detections


def perk_slots_capture_region(slot_centers, slot_size):
    width, height = slot_size
    left = min(center[0] - width / 2 for center in slot_centers)
    top = min(center[1] - height / 2 for center in slot_centers)
    right = max(center[0] + width / 2 for center in slot_centers)
    bottom = max(center[1] + height / 2 for center in slot_centers)
    return (
        int(round(left)),
        int(round(top)),
        int(round(right - left)),
        int(round(bottom - top)),
    )


def centers_relative_to_region(slot_centers, region):
    left, top, _width, _height = region
    return tuple((center[0] - left, center[1] - top) for center in slot_centers)


def available_perks_for_runtime(detections, slot_count=2):
    by_slot = {detection.slot_number: detection for detection in detections or []}
    values = []
    for slot_number in range(1, slot_count + 1):
        detection = by_slot.get(slot_number)
        if detection is not None and detection.available:
            values.append(detection.perk_key)
        else:
            values.append(PERK_NONE)
    return tuple(values)


def mark_perk_slot_used(detections, slot_number, expected_perk_key=None):
    updated = []
    changed = False
    for detection in detections or []:
        if detection.slot_number != slot_number:
            updated.append(detection)
            continue
        if expected_perk_key not in (None, PERK_NONE) and detection.perk_key != expected_perk_key:
            updated.append(detection)
            continue
        if not detection.available:
            updated.append(detection)
            continue
        updated.append(replace(detection, status=PERK_STATUS_USED))
        changed = True
    return updated, changed
