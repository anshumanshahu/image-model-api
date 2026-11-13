import sys
import pytesseract
from pytesseract import Output
from PIL import Image, ImageOps, ImageFilter, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

MIN_CONF = 45          # words below this confidence are dropped as noise
TIMEOUT = 20           # seconds per Tesseract run

# (image variant, language, page segmentation mode)
CANDIDATES = [
    ("gray", "eng", 6),
    ("gray", "eng+hin", 6),
    ("gray", "hin", 6),
    ("inverted", "eng", 6),   
    ("gray", "eng", 11),      
]


def available_langs():
    try:
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return set()


def _usable_candidates():
    langs = available_langs()
    return [c for c in CANDIDATES if all(part in langs for part in c[1].split("+"))]


def _variants(img):
    g = ImageOps.grayscale(img)
    longest = max(g.size)
    if longest < 1200:
        g = g.resize((g.width * 2, g.height * 2), Image.LANCZOS)
    elif longest > 2600:
        g.thumbnail((2600, 2600))
    g = ImageOps.autocontrast(g).filter(ImageFilter.SHARPEN)
    return {"gray": g, "inverted": ImageOps.invert(g)}


def _run(image, lang, psm):
    data = pytesseract.image_to_data(
        image, lang=lang, config=f"--psm {psm}",
        output_type=Output.DICT, timeout=TIMEOUT,
    )
    words, score = [], 0.0
    for text, conf in zip(data["text"], data["conf"]):
        text = text.strip()
        try:
            conf = float(conf)
        except (TypeError, ValueError):
            continue
        if text and conf >= MIN_CONF:
            words.append(text)
            score += conf
    return " ".join(words), score


def extract_text(img):
    """Return the text found in a PIL image ('' if nothing readable)."""
    variants = _variants(img.convert("RGB"))
    best_text, best_score = "", 0.0
    for name, lang, psm in _usable_candidates():
        try:
            text, score = _run(variants[name], lang, psm)
        except Exception:
            continue
        if score > best_score:
            best_text, best_score = text, score
    return best_text


if __name__ == "__main__":
    print("Tesseract languages:", sorted(available_langs()) or "NONE FOUND")
    if len(sys.argv) > 1:
        picture = Image.open(sys.argv[1])
        for name, lang, psm in _usable_candidates():
            try:
                text, score = _run(_variants(picture.convert("RGB"))[name], lang, psm)
                print(f"\n[{name} | {lang} | psm {psm} | score {score:.0f}]\n{text or '(nothing)'}")
            except Exception as e:
                print(f"\n[{name} | {lang} | psm {psm}] failed: {e}")
        print("\nFINAL:", extract_text(picture) or "(nothing)")