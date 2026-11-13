import os
import unicodedata
import joblib
import torch
import httpx
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image, ImageFile
from transformers import CLIPModel, CLIPProcessor

from ocr import extract_text, available_langs
from pii import find_pii

ImageFile.LOAD_TRUNCATED_IMAGES = True

TEXT_MANY_URL = os.getenv("TEXT_SERVICE_MANY_URL", "http://127.0.0.1:8001/check-text-many")

REVIEW_TH = 0.50
HIGH_CHANCE_TH = 0.80
MIN_OCR_WORDS = 3
CHUNK_WORDS, CHUNK_STEP = 8, 4


SCORE_KEYS = {
    "explicit": "NSFW",
    "suggestive": "NSFW",
    "offensive_gesture": "hate_gesture",
    "hate_symbol": "hate_symbol",
    "safe": "normal",
}


REASON_FOR = {
    "NSFW": "possible_nsfw",
    "hate_gesture": "possible_hate_gesture",
    "hate_symbol": "possible_hate_symbol",
}

MODEL = "openai/clip-vit-base-patch32"
clip = CLIPModel.from_pretrained(MODEL).eval()
proc = CLIPProcessor.from_pretrained(MODEL)
bundle = joblib.load("image_model.pkl")
clf, classes = bundle["clf"], bundle["classes"]

app = FastAPI(title="Image Moderation Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def classify(img):
    with torch.no_grad():
        f = clip.get_image_features(**proc(images=[img], return_tensors="pt"))
    if not torch.is_tensor(f):
        f = f.pooler_output
    f = (f / f.norm(dim=-1, keepdim=True)).numpy()
    return dict(zip(classes, clf.predict_proba(f)[0]))


def grouped_scores(probs):
    """Model classes ko response keys me map karo. Ek key ke liye max score lete hain."""
    out = {"NSFW": 0.0, "hate_gesture": 0.0, "hate_symbol": 0.0, "normal": 0.0}
    for cls, p in probs.items():
        key = SCORE_KEYS.get(cls)
        if key:
            out[key] = max(out[key], float(p))
    return {k: round(v, 4) for k, v in out.items()}


def word_chars(token):
    
    return sum(ch.isalnum() or unicodedata.category(ch).startswith("M") for ch in token)


def clean_ocr(text):
    """Stray symbols aur single characters hatao jo OCR picture se utha leta hai."""
    return " ".join(tok for tok in text.split() if word_chars(tok) >= 2)


def make_chunks(text):
    """Poora text + chhote overlapping tukde, taaki ek abusive line lambe text me chhup na jaye."""
    words = text.split()
    pieces = [text]
    if len(words) > CHUNK_WORDS:
        for i in range(0, len(words), CHUNK_STEP):
            window = words[i:i + CHUNK_WORDS]
            if len(window) >= MIN_OCR_WORDS:
                pieces.append(" ".join(window))
    return pieces


def build_response(probs, pii, raw_text, text, text_res):
    scores = grouped_scores(probs)

    # reasons
    reasons = [REASON_FOR[k] for k in REASON_FOR if scores[k] >= REVIEW_TH]

    text_pii = bool(text_res) and text_res.get("reason") == "personal_info"
    if pii or text_pii:
        reasons.append("possible_personal_info")
    elif text_res and text_res.get("status") in ("review", "reject"):
        reasons.append("possible_text_abuse")

    
    decision = "pending_review" if reasons else "allow"

    
    text_prob = float(text_res.get("probability", 0)) if text_res and "probability" in text_res else 0.0
    top_unsafe = max(scores["NSFW"], scores["hate_gesture"], scores["hate_symbol"], text_prob)
    high = bool(pii) or text_pii or top_unsafe >= HIGH_CHANCE_TH
    priority = "high_chance" if high else "low_chance"

    
    if pii:
        ocr_text = raw_text
        pii_found = pii
    elif text_pii:
        ocr_text = text
        pii_found = ["phone_or_email"]
    else:
        ocr_text = text
        pii_found = []

    return {
        "decision": decision,
        "reason": reasons,
        "scores": scores,
        "priority": priority,
        "ocr": {"text": ocr_text, "pii_found": pii_found},
    }


@app.get("/health")
def health():
    return {"status": "ok", "ocr_languages": sorted(available_langs())}


@app.post("/check-image")
def check_image(file: UploadFile = File(...)):
    try:
        img = Image.open(file.file).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image file")

    
    probs = classify(img)

    
    try:
        raw_text = extract_text(img)
    except Exception:
        raw_text = ""

    
    pii = find_pii(raw_text)

    
    text = clean_ocr(raw_text)
    text_res = None
    if not pii and len(text.split()) >= MIN_OCR_WORDS:
        try:
            r = httpx.post(TEXT_MANY_URL, json={"texts": make_chunks(text)}, timeout=15)
            text_res = r.json()
        except Exception:
            text_res = {"status": "unavailable"}

    return build_response(probs, pii, raw_text, text, text_res)