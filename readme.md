# Image Moderation Service

A small API that checks uploaded images and text inside them. It does not block content on its own. Anything that looks unsafe is sent to `pending_review`, so a person makes the final call.

## What it checks

- **The image itself:** NSFW, hate symbols, offensive gestures.
- **Text inside the image:** read with OCR (English and Hindi), then checked for abusive content.
- **Personal information:** phone numbers and email addresses in the text.

## Project files

```
image_service/
├── app.py              # the API
├── ocr.py              # text reading from images
├── pii.py              # phone and email detection
├── image_model.pkl     # trained image classifier
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup

You need Python 3.12 or newer, and Tesseract for OCR.

### 1. Install Tesseract

Ubuntu 
```bash
sudo apt install tesseract-ocr tesseract-ocr-hin
tesseract --list-langs
```

The second command must list `eng` and `hin`. If it does not, the OCR part will not work.

### 2. Create the virtual environment

```bash
cd image_service
python3 -m venv venv
source venv/bin/activate
```

### 3. Install PyTorch (CPU version)

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

Install torch with this command first. It is kept out of `requirements.txt` on purpose, so the CPU build is used and the large GPU packages are not downloaded.

### 4. Install the other packages

```bash
pip install -r requirements.txt
```

### 5. Download the image model (first time only)

The API uses a pretrained image model that is downloaded once from Hugging Face (about 600 MB):

```bash
python -c "from transformers import CLIPModel, CLIPProcessor; m='openai/clip-vit-base-patch32'; CLIPModel.from_pretrained(m); CLIPProcessor.from_pretrained(m); print('done')"
```

Wait until `done` is printed. Internet is needed for this step only. If the download stops, run the command again, and it continues from where it stopped.

### 6. Check the trained model file

`image_model.pkl` must be in the same folder as `app.py`. Check that it loads:

```bash
python -c "import joblib; b=joblib.load('image_model.pkl'); print(b['classes'])"
```

## Run

Start the text service first, if you want the text inside images to be checked. It runs on port 8001 by default.

Then start this service:

```bash
uvicorn app:app --port 8002
```

If the text service is somewhere else, set its address before starting:

```bash
export TEXT_SERVICE_MANY_URL=http://127.0.0.1:8001/check-text-many
```

Check that the service is running:

```bash
curl http://127.0.0.1:8002/health
```

Interactive docs: http://127.0.0.1:8002/docs

## Test

Upload an image with curl:

```bash
curl -X POST http://127.0.0.1:8002/check-image -F "file=@photo.jpg"
```

Or open `/docs`, use `POST /check-image`, click **Try it out**, choose a file, and click **Execute**.

## Response

```json
{
  "decision": "pending_review",
  "reason": ["possible_personal_info"],
  "scores": {
    "NSFW": 0.0034,
    "hate_gesture": 0.1865,
    "hate_symbol": 0.0009,
    "normal": 0.8092
  },
  "priority": "high_chance",
  "ocr": {
    "text": "9876546881 pst -",
    "pii_found": ["phone"]
  }
}
```

| Field | Meaning |
|---|---|
| `decision` | `allow` if nothing was flagged, `pending_review` if anything was flagged |
| `reason` | Why it was flagged. Can be more than one |
| `scores` | Scores for NSFW, hate gesture, hate symbol and normal content |
| `priority` | `high_chance` or `low_chance` |
| `ocr.text` | Text read from the image |
| `ocr.pii_found` | Type of personal data found: `phone`, `email`, or `phone_or_email` |

### Reason values

| Reason | When |
|---|---|
| `possible_nsfw` | NSFW score is 0.50 or more |
| `possible_hate_gesture` | Hate gesture score is 0.50 or more |
| `possible_hate_symbol` | Hate symbol score is 0.50 or more |
| `possible_personal_info` | Phone number or email found in the image text |
| `possible_text_abuse` | The text checker flagged the image text |

### Priority

`high_chance` is set when personal information is found, or when any score is 0.80 or more. Otherwise it is `low_chance`.

## Privacy

Personal data is returned as it is, so the response is sensitive:

- The `ocr.text` field can contain a full phone number or email address.
- Only send this response to an authorised reviewer or an internal review system.
