from __future__ import annotations

import logging
from typing import Iterable

import numpy as np
import torch
from PIL import Image

log = logging.getLogger(__name__)

_CLIP_MODEL_NAME = "ViT-H-14"
_CLIP_PRETRAINED = "laion2b_s32b_b79k"

_clip_cache: dict[str, tuple] = {}


def _load_clip() -> tuple:
    """Lazy-load open_clip ViT-H/14 (native 1024-dim output).

    Returns:
        ``(model, preprocess, device)`` tuple cached at module level.
    """
    key = f"{_CLIP_MODEL_NAME}/{_CLIP_PRETRAINED}"
    if key not in _clip_cache:
        import open_clip

        device = "cuda" if torch.cuda.is_available() else "cpu"
        log.info("loading clip model", extra={"model": key, "device": device})
        model, _, preprocess = open_clip.create_model_and_transforms(
            _CLIP_MODEL_NAME, pretrained=_CLIP_PRETRAINED, device=device
        )
        model.eval()
        if device == "cuda":
            model.half()
            log.info("clip model cast to float16", extra={"model": key})
        _clip_cache[key] = (model, preprocess, device)
    return _clip_cache[key]


def encode_images(
    images: Iterable[Image.Image],
    *,
    batch_size: int = 16,
) -> np.ndarray:
    """Encode a sequence of PIL images with open_clip ViT-H/14.

    Each image is preprocessed, run through the CLIP image encoder, and the
    per-image embedding is L2-normalized. The returned array preserves input
    order.

    Args:
        images:     Iterable of PIL images.
        batch_size: Encoder batch size.

    Returns:
        Float32 ndarray of shape ``(n_images, 1024)`` with row-wise L2 norm 1.
    """
    model, preprocess, device = _load_clip()
    image_list = list(images)
    if not image_list:
        return np.zeros((0, 1024), dtype=np.float32)

    tensors = torch.stack([preprocess(img) for img in image_list]).to(device)
    if device == "cuda":
        tensors = tensors.half()

    feats: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, len(tensors), batch_size):
            batch = tensors[start:start + batch_size]
            f = model.encode_image(batch)
            feats.append(f.float())
    frame_feats = torch.cat(feats, dim=0)
    frame_feats = frame_feats / frame_feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    return frame_feats.cpu().numpy().astype(np.float32)
