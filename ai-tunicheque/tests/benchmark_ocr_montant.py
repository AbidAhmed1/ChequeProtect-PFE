"""
tests/benchmark_ocr_montant.py
═══════════════════════════════════════════════════════
Benchmark complet de tous les OCR pour lire le montant manuscrit
sur les chèques tunisiens.

OBJECTIF : trouver quel OCR lit le montant en chiffres à 100%

USAGE :
    python tests/benchmark_ocr_montant.py \
        --image "Chequetest/chequeN.jpg" \
        --montant_reel 958.500

CONFIGURATION .env :
    OPENROUTER_API_KEY=sk-or-v1-XXX    # openrouter.ai (GRATUIT)
    GEMINI_API_KEY=AIzaSy-XXX          # aistudio.google.com (GRATUIT)
    ANTHROPIC_API_KEY=sk-ant-XXX       # console.anthropic.com
    MISTRAL_API_KEY=XXX                # console.mistral.ai
    OCRSPACE_API_KEY=XXX               # ocr.space (GRATUIT)
    VERYFI_CLIENT_ID=XXX               # veryfi.com (trial)
    VERYFI_CLIENT_SECRET=XXX
    VERYFI_USERNAME=XXX
    VERYFI_API_KEY=XXX
    NANONETS_API_KEY=XXX               # nanonets.com (14 jours)
    GOOGLE_VISION_KEY=XXX              # cloud.google.com

ORDRE DE TEST (du plus recommandé) :
  GRATUIT API  : Qwen2.5-VL-72B, Gemini 2.0, Deepseek, OCR.space
  GRATUIT LOCAL: Surya, Doctr, EasyOCR, Tesseract, LayoutLM
  PAYANT TRIAL : Veryfi (chèques), Nanonets, Transkribus, Rossum
"""

import os
import re
import sys
import json
import time
import base64
import argparse
import requests
import cv2
import numpy as np
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()


# ══════════════════════════════════════════════════════════════════
#  UTILITAIRES
# ══════════════════════════════════════════════════════════════════

def encoder_image(image_path: str, qualite: int = 95) -> tuple:
    """Encode l'image en base64 + retourne le crop de la zone montant."""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Image non trouvée : {image_path}")

    h, w = img.shape[:2]
    crop = img[0:int(h * 0.55), :]  # Zone haute = zone montant

    enc = [int(cv2.IMWRITE_JPEG_QUALITY), qualite]
    _, buf_full = cv2.imencode('.jpg', img, enc)
    _, buf_crop = cv2.imencode('.jpg', crop, enc)

    b64_full = base64.b64encode(buf_full).decode('utf-8')
    b64_crop = base64.b64encode(buf_crop).decode('utf-8')
    return b64_full, b64_crop, crop, img


def extraire_montant(texte: str) -> str:
    """Extrait un nombre depuis une réponse texte."""
    if not texte:
        return ""
    texte = str(texte).strip()
    # Chercher un pattern entre # si présent
    m = re.search(r'#([\d,. ]+)#', texte)
    if m:
        texte = m.group(1).strip()

    # Extraire les chiffres avec virgule/point
    m2 = re.search(r'(\d{1,6}[,.]?\d{0,3})', texte.replace(' ', ''))
    if m2:
        val = m2.group(1).replace(',', '.')
        try:
            return str(round(float(val), 3))
        except:
            pass
    return ""


def evaluer(resultat: str, montant_reel: float) -> dict:
    """Évalue la précision d'un résultat."""
    if not resultat:
        return {"correct": False, "erreur_pct": None, "note": "non extrait"}
    try:
        val = float(resultat)
        if montant_reel > 0:
            erreur = abs(val - montant_reel) / montant_reel * 100
            correct = erreur < 2.0  # Tolérance 2%
            return {
                "correct": correct,
                "erreur_pct": round(erreur, 2),
                "note": f"{'✓' if correct else '✗'} {val} vs {montant_reel} (erreur={erreur:.1f}%)"
            }
    except:
        pass
    return {"correct": False, "erreur_pct": None, "note": f"invalide: {resultat}"}


PROMPT_FR = (
    "Sur ce chèque tunisien, lis le montant écrit à la main entre les # (dièse). "
    "Exemple : #958,500# → réponse : 958,500. "
    "Réponds UNIQUEMENT par le chiffre. "
    "Si aucun montant visible entre # : réponds 0"
)

PROMPT_EN = (
    "This is a Tunisian bank cheque. "
    "Find the handwritten amount between # symbols. "
    "Example: #958,500# means amount is 958,500. "
    "Reply ONLY with the number. If no amount between #: reply 0"
)


# ══════════════════════════════════════════════════════════════════
#  GROUPE 1 : GRATUIT API (sans installation locale)
# ══════════════════════════════════════════════════════════════════

def test_qwen_openrouter(b64_crop: str) -> dict:
    """
    Qwen2.5-VL-72B via OpenRouter — GRATUIT
    Inscription : https://openrouter.ai
    Clé dans .env : OPENROUTER_API_KEY=sk-or-v1-XXX
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "OPENROUTER_API_KEY manquante dans .env"}

    t0 = time.time()
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://tunicheque.tn"},
            json={"model": "qwen/qwen2.5-vl-72b-instruct:free",
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": PROMPT_EN},
                      {"type": "image_url", "image_url": {
                          "url": f"data:image/jpeg;base64,{b64_crop}"
                      }}
                  ]}],
                  "temperature": 0.0, "max_tokens": 20},
            timeout=35
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["choices"][0]["message"]["content"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_deepseek_openrouter(b64_crop: str) -> dict:
    """
    Deepseek-VL2 via OpenRouter — GRATUIT
    Même clé OpenRouter que Qwen
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "OPENROUTER_API_KEY manquante"}

    t0 = time.time()
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json",
                     "HTTP-Referer": "https://tunicheque.tn"},
            json={"model": "deepseek/deepseek-vl2:free",
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": PROMPT_EN},
                      {"type": "image_url", "image_url": {
                          "url": f"data:image/jpeg;base64,{b64_crop}"
                      }}
                  ]}],
                  "temperature": 0.0, "max_tokens": 20},
            timeout=35
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["choices"][0]["message"]["content"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_llama_openrouter(b64_crop: str) -> dict:
    """
    Llama 3.2 Vision 90B via OpenRouter — GRATUIT
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "OPENROUTER_API_KEY manquante"}

    t0 = time.time()
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": "meta-llama/llama-3.2-90b-vision-instruct:free",
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": PROMPT_EN},
                      {"type": "image_url", "image_url": {
                          "url": f"data:image/jpeg;base64,{b64_crop}"
                      }}
                  ]}],
                  "temperature": 0.0, "max_tokens": 20},
            timeout=35
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["choices"][0]["message"]["content"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_gemini(b64_crop: str) -> dict:
    """
    Google Gemini 2.0 Flash — GRATUIT 1500 req/jour
    Clé : https://aistudio.google.com/app/apikey
    Dans .env : GEMINI_API_KEY=AIzaSy-XXX
    """
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "GEMINI_API_KEY manquante dans .env"}

    t0 = time.time()
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/gemini-2.0-flash:generateContent?key={key}",
            headers={"Content-Type": "application/json"},
            json={"contents": [{"parts": [
                {"text": PROMPT_EN},
                {"inline_data": {"mime_type": "image/jpeg", "data": b64_crop}}
            ]}],
                "generationConfig": {"temperature": 0.0, "maxOutputTokens": 20}},
            timeout=20
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_claude(b64_crop: str) -> dict:
    """
    Claude Sonnet 4 Vision (Anthropic)
    Clé : https://console.anthropic.com
    Dans .env : ANTHROPIC_API_KEY=sk-ant-XXX
    """
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "ANTHROPIC_API_KEY manquante"}

    t0 = time.time()
    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json={"model": "claude-sonnet-4-20250514", "max_tokens": 20,
                  "messages": [{"role": "user", "content": [
                      {"type": "image", "source": {"type": "base64",
                                                   "media_type": "image/jpeg",
                                                   "data": b64_crop}},
                      {"type": "text", "text": PROMPT_FR}
                  ]}]},
            timeout=25
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["content"][0]["text"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_mistral(b64_crop: str) -> dict:
    """
    Mistral pixtral-large-latest
    Dans .env : MISTRAL_API_KEY=XXX
    """
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "MISTRAL_API_KEY manquante"}

    t0 = time.time()
    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={"model": "pixtral-large-latest",
                  "messages": [{"role": "user", "content": [
                      {"type": "text", "text": PROMPT_EN},
                      {"type": "image_url", "image_url": {
                          "url": f"data:image/jpeg;base64,{b64_crop}"
                      }}
                  ]}], "temperature": 0.0, "max_tokens": 20},
            timeout=35
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            rep = r.json()["choices"][0]["message"]["content"].strip()
            return {"statut": "OK", "brut": rep,
                    "montant": extraire_montant(rep), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_ocrspace(b64_crop: str, buf_crop: bytes) -> dict:
    """
    OCR.space — GRATUIT (25000 req/mois)
    Inscription : https://ocr.space/ocrapi
    Dans .env : OCRSPACE_API_KEY=XXX
    """
    key = os.environ.get("OCRSPACE_API_KEY", "helloworld")  # clé demo

    t0 = time.time()
    try:
        r = requests.post(
            "https://api.ocr.space/parse/image",
            data={
                "apikey": key,
                "language": "fre",
                "isOverlayRequired": False,
                "base64Image": f"data:image/jpeg;base64,{b64_crop}",
                "OCREngine": 2  # Engine 2 = meilleur pour manuscrit
            },
            timeout=30
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            data = r.json()
            if data.get("ParsedResults"):
                texte = data["ParsedResults"][0]["ParsedText"]
                return {"statut": "OK", "brut": texte[:200],
                        "montant": extraire_montant(texte), "ms": ms}
            return {"statut": "ERR", "detail": data.get("ErrorMessage"), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_google_vision(b64_full: str) -> dict:
    """
    Google Cloud Vision API
    Clé : https://cloud.google.com/vision → activer + créer clé API
    Dans .env : GOOGLE_VISION_KEY=XXX
    """
    key = os.environ.get("GOOGLE_VISION_KEY")
    if not key:
        return {"statut": "SKIP", "raison": "GOOGLE_VISION_KEY manquante"}

    t0 = time.time()
    try:
        r = requests.post(
            f"https://vision.googleapis.com/v1/images:annotate?key={key}",
            json={"requests": [{"image": {"content": b64_full},
                                "features": [{"type": "TEXT_DETECTION"}]}]},
            timeout=20
        )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            texts = r.json()["responses"][0].get("textAnnotations", [])
            if texts:
                texte = texts[0]["description"]
                return {"statut": "OK", "brut": texte[:300],
                        "montant": extraire_montant(texte), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_veryfi(image_path: str) -> dict:
    """
    Veryfi — spécialisé chèques bancaires
    Trial gratuit : https://veryfi.com
    Dans .env : VERYFI_CLIENT_ID, VERYFI_CLIENT_SECRET,
                VERYFI_USERNAME, VERYFI_API_KEY
    """
    client_id  = os.environ.get("VERYFI_CLIENT_ID")
    client_sec = os.environ.get("VERYFI_CLIENT_SECRET")
    username   = os.environ.get("VERYFI_USERNAME")
    api_key    = os.environ.get("VERYFI_API_KEY")

    if not all([client_id, client_sec, username, api_key]):
        return {"statut": "SKIP",
                "raison": "Clés Veryfi manquantes (VERYFI_CLIENT_ID/SECRET/USERNAME/API_KEY)"}

    t0 = time.time()
    try:
        import hmac, hashlib
        timestamp = str(int(time.time()))
        msg       = f"timestamp:{timestamp},username:{username}"
        signature = base64.b64encode(
            hmac.new(client_sec.encode(), msg.encode(), hashlib.sha256).digest()
        ).decode()

        with open(image_path, "rb") as f:
            r = requests.post(
                "https://api.veryfi.com/api/v8/partner/checks/",
                headers={"CLIENT-ID": client_id,
                         "AUTHORIZATION": f"apikey {username}:{api_key}",
                         "Accept": "application/json"},
                files={"file": (Path(image_path).name, f, "image/jpeg")},
                timeout=40
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code in (200, 201):
            data = r.json()
            amount = data.get("amount") or data.get("total") or ""
            return {"statut": "OK", "brut": str(data)[:200],
                    "montant": str(amount), "ms": ms}
        return {"statut": "ERR", "code": r.status_code,
                "detail": r.text[:100], "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_nanonets(image_path: str) -> dict:
    """
    Nanonets OCR — 14 jours gratuits
    Inscription : https://nanonets.com
    Dans .env : NANONETS_API_KEY=XXX
    Note : il faut créer un modèle "chèque" dans l'interface Nanonets
           et récupérer le model_id
    """
    key = os.environ.get("NANONETS_API_KEY")
    model_id = os.environ.get("NANONETS_MODEL_ID", "")

    if not key:
        return {"statut": "SKIP", "raison": "NANONETS_API_KEY manquante"}
    if not model_id:
        return {"statut": "SKIP",
                "raison": "NANONETS_MODEL_ID manquant (créer un modèle sur nanonets.com)"}

    t0 = time.time()
    try:
        with open(image_path, "rb") as f:
            r = requests.post(
                f"https://app.nanonets.com/api/v2/OCR/Model/{model_id}/LabelFile/",
                auth=requests.auth.HTTPBasicAuth(key, ""),
                files={"file": (Path(image_path).name, f, "image/jpeg")},
                timeout=45
            )
        ms = int((time.time() - t0) * 1000)
        if r.status_code == 200:
            data = r.json()
            # Chercher le champ montant dans les prédictions
            fields = {}
            for result in data.get("result", []):
                for pred in result.get("prediction", []):
                    fields[pred.get("label")] = pred.get("ocr_text")
            montant = fields.get("montant") or fields.get("amount") or ""
            return {"statut": "OK", "brut": str(fields)[:200],
                    "montant": extraire_montant(montant), "ms": ms}
        return {"statut": "ERR", "code": r.status_code, "ms": ms}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


# ══════════════════════════════════════════════════════════════════
#  GROUPE 2 : GRATUIT LOCAL (installation pip)
# ══════════════════════════════════════════════════════════════════

def test_easyocr(crop: np.ndarray) -> dict:
    """
    EasyOCR — pip install easyocr
    Offline, gratuit, modèle FR+EN
    """
    t0 = time.time()
    try:
        import easyocr
        reader = easyocr.Reader(['fr', 'en'], gpu=False, verbose=False)
        resultats = reader.readtext(crop, detail=0)
        ms = int((time.time() - t0) * 1000)
        texte = " ".join(resultats)
        return {"statut": "OK", "brut": texte[:200],
                "montant": extraire_montant(texte), "ms": ms}
    except ImportError:
        return {"statut": "SKIP",
                "raison": "pip install easyocr"}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_surya(image_path: str) -> dict:
    """
    Surya OCR — pip install surya-ocr
    État de l'art 2024 pour manuscrit
    Benchmark : https://github.com/VikParuchuri/surya
    """
    t0 = time.time()
    try:
        from surya.ocr import run_ocr
        from surya.model.detection.model import load_model as load_det
        from surya.model.detection.processor import load_processor as load_det_proc
        from surya.model.recognition.model import load_model as load_rec
        from surya.model.recognition.processor import load_processor as load_rec_proc
        from PIL import Image

        img = Image.open(image_path)
        h, w = img.size
        # Crop zone montant
        img_crop = img.crop((0, 0, w, int(h * 0.55)))

        det_model = load_det()
        det_proc  = load_det_proc()
        rec_model = load_rec()
        rec_proc  = load_rec_proc()

        resultats = run_ocr(
            [img_crop], [["fr", "en"]],
            det_model, det_proc, rec_model, rec_proc
        )
        ms = int((time.time() - t0) * 1000)
        texte = " ".join(r.text for page in resultats for r in page.text_lines)
        return {"statut": "OK", "brut": texte[:200],
                "montant": extraire_montant(texte), "ms": ms}
    except ImportError:
        return {"statut": "SKIP",
                "raison": "pip install surya-ocr"}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_doctr(crop: np.ndarray) -> dict:
    """
    Doctr (Deep OCR Toolkit) — pip install python-doctr
    Microsoft, spécialisé documents financiers
    """
    t0 = time.time()
    try:
        from doctr.models import ocr_predictor
        from doctr.io import DocumentFile

        # Sauvegarder le crop temp
        tmp = "/tmp/crop_doctr.jpg"
        cv2.imwrite(tmp, crop)
        doc = DocumentFile.from_images([tmp])
        model = ocr_predictor(pretrained=True)
        result = model(doc)
        ms = int((time.time() - t0) * 1000)
        texte = " ".join(
            w.value for page in result.pages
            for block in page.blocks
            for line in block.lines
            for w in line.words
        )
        return {"statut": "OK", "brut": texte[:200],
                "montant": extraire_montant(texte), "ms": ms}
    except ImportError:
        return {"statut": "SKIP",
                "raison": "pip install python-doctr[torch]"}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


def test_tesseract(crop: np.ndarray) -> dict:
    """
    Tesseract OCR — pip install pytesseract
    + installer Tesseract : https://github.com/tesseract-ocr/tesseract
    Windows : https://github.com/UB-Mannheim/tesseract/wiki
    """
    t0 = time.time()
    try:
        import pytesseract
        from PIL import Image

        # Config pour lire uniquement des chiffres et virgules
        config = '--psm 7 -c tessedit_char_whitelist=0123456789,.'
        img_pil = Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        texte = pytesseract.image_to_string(img_pil, lang='fra', config=config)
        ms = int((time.time() - t0) * 1000)
        return {"statut": "OK", "brut": texte.strip()[:200],
                "montant": extraire_montant(texte), "ms": ms}
    except ImportError:
        return {"statut": "SKIP",
                "raison": "pip install pytesseract + installer Tesseract.exe"}
    except Exception as e:
        return {"statut": "EXCEPTION", "detail": str(e)[:80]}


# ══════════════════════════════════════════════════════════════════
#  BENCHMARK PRINCIPAL
# ══════════════════════════════════════════════════════════════════

TESTS = [
    # (nom_affichage, categorie, fonction)
    ("Qwen2.5-VL-72B (OpenRouter)",  "GRATUIT API",   lambda b64f, b64c, crop, img, path: test_qwen_openrouter(b64c)),
    ("Gemini 2.0 Flash (Google)",    "GRATUIT API",   lambda b64f, b64c, crop, img, path: test_gemini(b64c)),
    ("Deepseek-VL2 (OpenRouter)",    "GRATUIT API",   lambda b64f, b64c, crop, img, path: test_deepseek_openrouter(b64c)),
    ("Llama 3.2 Vision (OpenRouter)","GRATUIT API",   lambda b64f, b64c, crop, img, path: test_llama_openrouter(b64c)),
    ("OCR.space (Engine 2)",         "GRATUIT API",   lambda b64f, b64c, crop, img, path: test_ocrspace(b64c, None)),
    ("Google Cloud Vision",          "GRATUIT API",   lambda b64f, b64c, crop, img, path: test_google_vision(b64f)),
    ("Claude Sonnet 4 Vision",       "PAYANT API",    lambda b64f, b64c, crop, img, path: test_claude(b64c)),
    ("Mistral pixtral-large",        "PAYANT API",    lambda b64f, b64c, crop, img, path: test_mistral(b64c)),
    ("Veryfi (chèques)",             "PAYANT TRIAL",  lambda b64f, b64c, crop, img, path: test_veryfi(path)),
    ("Nanonets",                     "PAYANT TRIAL",  lambda b64f, b64c, crop, img, path: test_nanonets(path)),
    ("EasyOCR (local)",              "GRATUIT LOCAL", lambda b64f, b64c, crop, img, path: test_easyocr(crop)),
    ("Surya OCR (local)",            "GRATUIT LOCAL", lambda b64f, b64c, crop, img, path: test_surya(path)),
    ("Doctr (local)",                "GRATUIT LOCAL", lambda b64f, b64c, crop, img, path: test_doctr(crop)),
    ("Tesseract (local)",            "GRATUIT LOCAL", lambda b64f, b64c, crop, img, path: test_tesseract(crop)),
]


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark OCR montant manuscrit chèques tunisiens")
    parser.add_argument("--image",   required=True,  help="Chemin vers l'image du chèque recto")
    parser.add_argument("--montant_reel", type=float, default=0.0,
                        help="Montant réel du chèque (ex: 958.500)")
    parser.add_argument("--only",    nargs="+",       help="Tester uniquement ces OCR")
    args = parser.parse_args()

    if not Path(args.image).exists():
        print(f"❌ Image non trouvée : {args.image}")
        sys.exit(1)

    print()
    print("╔" + "═" * 68 + "╗")
    print("║        BENCHMARK OCR — LECTURE MONTANT MANUSCRIT CHÈQUE TN       ║")
    print("╚" + "═" * 68 + "╝")
    print(f"  Image        : {args.image}")
    print(f"  Montant réel : {args.montant_reel} DT")
    print(f"  Date         : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("─" * 70)

    b64_full, b64_crop, crop, img = encoder_image(args.image)
    print(f"  Crop zone montant (55% haut) : {crop.shape[1]}x{crop.shape[0]} px")
    print()

    resultats = []
    cat_courante = None

    for nom, categorie, fn in TESTS:
        if args.only and not any(o.lower() in nom.lower() for o in args.only):
            continue

        if categorie != cat_courante:
            cat_courante = categorie
            print(f"\n  ── {categorie} {'─' * (45 - len(categorie))}")

        print(f"  ⏳ {nom:<35}", end="", flush=True)
        try:
            res = fn(b64_full, b64_crop, crop, img, args.image)
        except Exception as e:
            res = {"statut": "EXCEPTION", "detail": str(e)[:60]}

        montant = res.get("montant", "")
        eval_res = evaluer(montant, args.montant_reel) if args.montant_reel > 0 else {}
        ms = res.get("ms", 0)

        if res["statut"] == "SKIP":
            print(f"⏭  SKIP — {res.get('raison','')[:50]}")
            icone = "⏭"
        elif res["statut"] == "OK":
            if montant:
                correct = eval_res.get("correct", False)
                erreur = eval_res.get("erreur_pct", "?")
                icone = "✅" if correct else "⚠️ "
                print(f"{icone} {montant:<12} brut='{res.get('brut','')[:30]}'  "
                      f"err={erreur}%  {ms}ms")
            else:
                icone = "❌"
                print(f"❌ (non extrait)  brut='{res.get('brut','')[:40]}'  {ms}ms")
        else:
            icone = "⛔"
            print(f"⛔ {res['statut']} — {res.get('detail', res.get('code',''))[:50]}")

        resultats.append({
            "ocr": nom,
            "categorie": categorie,
            "statut": res["statut"],
            "montant": montant,
            "brut": res.get("brut", "")[:100],
            "ms": ms,
            "icone": icone,
            **eval_res
        })

    # ─── Tableau récapitulatif ────────────────────────────────────
    print()
    print("═" * 70)
    print(f"  {'RÉSULTATS PAR PRÉCISION':^66}")
    print("═" * 70)

    ok = [r for r in resultats if r.get("correct")]
    warn = [r for r in resultats if r["montant"] and not r.get("correct")]
    skip = [r for r in resultats if r["statut"] == "SKIP"]
    err  = [r for r in resultats if r["statut"] not in ("OK","SKIP")]

    print(f"\n  ✅ CORRECTS ({len(ok)}) :")
    for r in sorted(ok, key=lambda x: x.get("erreur_pct", 999)):
        print(f"     {r['ocr']:<35} → {r['montant']:<12} err={r.get('erreur_pct')}%  {r['ms']}ms")

    print(f"\n  ⚠️  PROCHES ({len(warn)}) :")
    for r in sorted(warn, key=lambda x: x.get("erreur_pct", 999) or 999):
        print(f"     {r['ocr']:<35} → {r['montant']:<12} err={r.get('erreur_pct')}%")

    if err:
        print(f"\n  ⛔ ERREURS ({len(err)}) :")
        for r in err:
            print(f"     {r['ocr']:<35} → {r['statut']}")

    print(f"\n  ⏭  IGNORÉS (clé manquante) ({len(skip)}) :")
    for r in skip:
        print(f"     {r['ocr']}")

    # ─── Sauvegarde JSON ─────────────────────────────────────────
    rapport = {
        "image": args.image,
        "montant_reel": args.montant_reel,
        "date": datetime.now().isoformat(),
        "resultats": resultats
    }
    sortie = Path("benchmark_ocr.json")
    sortie.write_text(json.dumps(rapport, indent=2, ensure_ascii=False),
                      encoding="utf-8")
    print(f"\n  💾 Résultats complets → {sortie}")

    # Recommandation finale
    if ok:
        meilleur = sorted(ok, key=lambda x: x.get("erreur_pct", 999))[0]
        print()
        print(f"  🏆 MEILLEUR OCR : {meilleur['ocr']}")
        print(f"     Montant lu   : {meilleur['montant']}")
        print(f"     Erreur       : {meilleur.get('erreur_pct')}%")
        print(f"     Temps        : {meilleur['ms']} ms")
    print()


if __name__ == "__main__":
    main()