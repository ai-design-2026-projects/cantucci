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
_tokenizer_cache: dict[str, object] = {}


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


def _load_clip_tokenizer():
    """Lazy-load the open_clip tokenizer for ViT-H/14.

    Returns:
        The cached tokenizer instance.
    """
    key = _CLIP_MODEL_NAME
    if key not in _tokenizer_cache:
        import open_clip

        log.info("loading clip tokenizer", extra={"model": key})
        _tokenizer_cache[key] = open_clip.get_tokenizer(key)
    return _tokenizer_cache[key]


def encode_texts(
    texts: list[str],
    *,
    batch_size: int = 64,
) -> np.ndarray:
    """Encode a list of text strings with the open_clip ViT-H/14 text tower.

    The output lives in the same embedding space as ``encode_images``, so the
    resulting vectors are directly comparable (cosine) to ``trailer_embedding``
    columns in the database. Each text is tokenized (truncated to the CLIP
    context length of 77 tokens), run through the text encoder, and L2-normalized.

    Args:
        texts:      List of input strings. Short visual phrases (3–8 words) work
                    best and stay safely within the 77-token context limit.
        batch_size: Encoder batch size.

    Returns:
        Float32 ndarray of shape ``(len(texts), 1024)`` with row-wise L2 norm 1.
        Returns a ``(0, 1024)`` array when *texts* is empty.
    """
    if not texts:
        return np.zeros((0, 1024), dtype=np.float32)

    model, _, device = _load_clip()
    tokenizer = _load_clip_tokenizer()

    tokens = tokenizer(texts)
    if device == "cuda":
        tokens = tokens.to(device)

    feats: list[torch.Tensor] = []
    with torch.no_grad():
        for start in range(0, len(tokens), batch_size):
            batch = tokens[start : start + batch_size]
            if device == "cuda":
                batch = batch.half()
            f = model.encode_text(batch)
            feats.append(f.float())

    text_feats = torch.cat(feats, dim=0)
    text_feats = text_feats / text_feats.norm(dim=-1, keepdim=True).clamp_min(1e-12)
    return text_feats.cpu().numpy().astype(np.float32)


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
