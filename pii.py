import re, unicodedata
import phonenumbers

DEV = str.maketrans("०१२३४५६७८९", "0123456789")

WORD_DIGITS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "shunya": "0", "ek": "1", "do": "2", "teen": "3", "char": "4", "chaar": "4",
    "paanch": "5", "panch": "5", "chhe": "6", "che": "6", "saat": "7", "sat": "7",
    "aath": "8", "ath": "8", "nau": "9",
}

EMAIL_RE = re.compile(r"[a-z0-9._%+\-]+@[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.[a-z]{2,}")


PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?|0)?([6-9](?:[\s\-]?\d){9})(?!\d)")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text).lower().translate(DEV)
    
    t = re.sub(
        r"\s*[\[\(]?\s*\b(?:at the rate|at)\b\s*[\]\)]?\s*"
        r"(?=[a-z0-9\-]+\s*[\[\(]?\s*(?:\bdot\b|\.))",
        "@", t,
    )
    t = re.sub(r"\s*[\[\(]?\s*\bdot\b\s*[\]\)]?\s*", ".", t)
    return t


def has_email(text: str) -> bool:
    return bool(EMAIL_RE.search(normalize(text)))


def has_phone(text: str) -> bool:
    t = normalize(text)
    
    t = re.sub(r"[a-z]+", lambda m: WORD_DIGITS.get(m.group(), m.group()), t)
    for m in PHONE_RE.finditer(t):
        digits = re.sub(r"\D", "", m.group(0))[-10:]
        try:
            if phonenumbers.is_valid_number(phonenumbers.parse("+91" + digits, None)):
                return True
        except phonenumbers.NumberParseException:
            pass
    return False


def find_pii(text: str) -> list:
    """['email'], ['phone'], both, or [] if clean."""
    found = []
    if has_email(text):
        found.append("email")
    if has_phone(text):
        found.append("phone")
    return found


def contains_contact_info(text: str) -> bool:
    return bool(find_pii(text))
