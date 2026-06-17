"""
Automatic image description (BLIP captioning) + translation.

Requires: torch, transformers, sentencepiece, sacremoses (heavy, ~1-2 GB
with model weights). Gracefully disabled if not installed, or if model
download fails (no internet on first use).
"""

try:
    import torch
    from PIL import Image
    from transformers import (
        BlipProcessor, BlipForConditionalGeneration,
        MarianMTModel, MarianTokenizer,
    )
    HAS_CAPTIONING = True
except ImportError:
    HAS_CAPTIONING = False

# Target languages available for translation. 'en' = keep the raw caption.
LANGUAGE_LABELS = {
    'en': 'Anglais (pas de traduction)',
    'fr': 'Français',
    'fi': 'Finnois',
}

_TRANSLATION_MODELS = {
    'fr': 'Helsinki-NLP/opus-mt-en-fr',
    'fi': 'Helsinki-NLP/opus-mt-en-fi',
}

# Lazily-loaded singletons, shared across all files in a processing run.
_caption_processor = None
_caption_model = None
_translators = {}  # lang code -> (tokenizer, model)


def _load_caption_model():
    global _caption_processor, _caption_model
    if _caption_model is None:
        _caption_processor = BlipProcessor.from_pretrained('Salesforce/blip-image-captioning-base')
        _caption_model = BlipForConditionalGeneration.from_pretrained('Salesforce/blip-image-captioning-base')
    return _caption_processor, _caption_model


def _load_translator(lang):
    if lang not in _TRANSLATION_MODELS:
        return None
    if lang not in _translators:
        model_name = _TRANSLATION_MODELS[lang]
        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        _translators[lang] = (tokenizer, model)
    return _translators[lang]


def generate_caption(image_path):
    """Return an English caption describing the image, or '' on failure."""
    if not HAS_CAPTIONING:
        return ''
    try:
        processor, model = _load_caption_model()
        image = Image.open(image_path).convert('RGB')
        inputs = processor(images=image, return_tensors='pt')
        with torch.no_grad():
            out = model.generate(**inputs)
        return processor.decode(out[0], skip_special_tokens=True)
    except Exception:
        return ''


def translate(text, lang):
    """Translate English text to `lang`. 'en' or failure = return as-is."""
    if not text or lang == 'en' or not HAS_CAPTIONING:
        return text
    try:
        pair = _load_translator(lang)
        if pair is None:
            return text
        tokenizer, model = pair
        batch = tokenizer([text], return_tensors='pt', padding=True)
        translated = model.generate(**batch)
        return tokenizer.batch_decode(translated, skip_special_tokens=True)[0]
    except Exception:
        return text


def describe_image(image_path, lang='fi'):
    """
    Generate a caption for an image, translated to `lang`.
    Returns (description, keywords) — keywords is a short list of words
    extracted from the description, used as EXIF tags when none exist yet.
    """
    caption_en = generate_caption(image_path)
    if not caption_en:
        return '', []
    description = translate(caption_en, lang)
    keywords = [w.strip('.,!?;:').lower() for w in description.split()][:5]
    keywords = [k for k in keywords if k]
    return description, keywords
