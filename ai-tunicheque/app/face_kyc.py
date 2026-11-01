"""
app/face_kyc.py — Moteur KYC Biometrique
==========================================
Face verification CIN tunisienne vs Selfie.
MTCNN (detection) + FaceNet512 (embeddings) + Cosine (comparaison).
OCR numero CIN (pytesseract).

Installer :
    pip install deepface mtcnn tensorflow opencv-python Pillow pytesseract
    Tesseract binary : https://github.com/UB-Mannheim/tesseract/wiki
"""

import cv2
import base64
import logging
import re
import time
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

# pytesseract optionnel — si absent, endpoint renvoie ocr_available=false
try:
    import pytesseract
    import os as _os
    # Chercher tesseract dans plusieurs emplacements courants
    for _p in [
        r"D:\tesseract\tesseract.exe",
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if _os.path.exists(_p):
            pytesseract.pytesseract.tesseract_cmd = _p
            break
    HAS_TESSERACT = True
    logging.getLogger(__name__).info(f"pytesseract disponible — cmd={pytesseract.pytesseract.tesseract_cmd}")
except ImportError:
    HAS_TESSERACT = False

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["KYC Biometrique"])

# ══════════════════════════════════════════════════════════════════
# PARAMETRES GLOBAUX
# ══════════════════════════════════════════════════════════════════
FACE_THRESHOLD   = 0.40   # Distance cosine max = meme personne (FaceNet512)
MIN_FACE_SIZE    = 40     # Pixels minimum du visage detecte
CIN_FACE_ZONE    = 0.40   # La photo est dans les 40% gauche de la CIN tunisienne


# ══════════════════════════════════════════════════════════════════
# PHASE 1 : DECODAGE + VALIDATION IMAGE
# ══════════════════════════════════════════════════════════════════

def _decode_image(raw_bytes: bytes, label: str) -> np.ndarray:
    """
    Decode les bytes en image OpenCV BGR.
    Valide que l'image n'est pas corrompue et a une resolution suffisante.
    """
    arr = np.frombuffer(raw_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    if img is None:
        raise ValueError(f"Image {label} illisible ou format non supporte")

    h, w = img.shape[:2]
    if h < 100 or w < 100:
        raise ValueError(f"Image {label} trop petite ({w}x{h}px — minimum 100x100)")

    # Reduction du bruit (aide MTCNN sur les CIN plastifiees)
    img = cv2.GaussianBlur(img, (3, 3), 0)
    img = cv2.GaussianBlur(img, (1, 1), 0)  # leger pour ne pas flouter les traits

    return img


# ══════════════════════════════════════════════════════════════════
# PHASE 2 : DETECTION + ALIGNEMENT DU VISAGE (MTCNN)
# MTCNN detecte les landmarks (yeux, nez, bouche) → alignement precis
# ══════════════════════════════════════════════════════════════════

def _extract_face_mtcnn(img_bgr: np.ndarray, label: str,
                         zone_gauche_only: bool = False) -> np.ndarray:
    """
    Detecte et extrait le visage avec MTCNN.
    Pour la CIN : cherche uniquement dans la zone gauche (photo du titulaire).
    Pour le selfie : cherche sur toute l'image.

    Retourne l'image du visage recadree et normalisee (160x160 pour FaceNet512).
    """
    from mtcnn import MTCNN
    detector = MTCNN()

    # Pour la CIN : isoler la zone portrait (gauche ~40%)
    if zone_gauche_only:
        h, w = img_bgr.shape[:2]
        region = img_bgr[:, :int(w * CIN_FACE_ZONE)]
    else:
        region = img_bgr

    # Convertir BGR → RGB (MTCNN attend RGB)
    img_rgb = cv2.cvtColor(region, cv2.COLOR_BGR2RGB)

    # Detection
    results = detector.detect_faces(img_rgb)

    if not results:
        # Fallback : zone fixe CIN tunisienne si MTCNN echoue
        if zone_gauche_only:
            logger.warning(f"MTCNN n'a pas detecte de visage sur {label} — fallback zone fixe")
            h, w = img_bgr.shape[:2]
            face_region = img_bgr[int(h*0.08):int(h*0.92), int(w*0.03):int(w*0.37)]
            if face_region.size == 0:
                raise ValueError(f"Aucun visage detecte sur la CIN ({label})")
            return cv2.resize(face_region, (160, 160))
        else:
            raise ValueError(f"Aucun visage detecte sur le selfie ({label}). "
                             "Assurez-vous d'etre bien eclaire et de regarder la camera.")

    # Prendre le visage le plus grand (confiance la plus haute)
    best = max(results, key=lambda r: r["confidence"])

    if best["confidence"] < 0.85:
        logger.warning(f"Confiance faible sur {label} : {best['confidence']:.2f}")

    x, y, fw, fh = best["box"]

    # Alignement par rotation basee sur les yeux
    keypoints = best["keypoints"]
    face_img  = _align_face(img_rgb, x, y, fw, fh, keypoints)

    # Normaliser a 160x160 (taille d'entree FaceNet512)
    return cv2.resize(face_img, (160, 160))


def _align_face(img_rgb: np.ndarray, x: int, y: int, fw: int, fh: int,
                keypoints: dict) -> np.ndarray:
    """
    Aligne le visage pour que les yeux soient horizontaux.
    Ameliore significativement la precision de FaceNet512.
    """
    left_eye  = keypoints["left_eye"]
    right_eye = keypoints["right_eye"]

    # Angle de rotation pour aligner les yeux horizontalement
    dy = right_eye[1] - left_eye[1]
    dx = right_eye[0] - left_eye[0]
    angle = np.degrees(np.arctan2(dy, dx))

    # Centre entre les deux yeux
    eye_center = (
        int((left_eye[0] + right_eye[0]) / 2),
        int((left_eye[1] + right_eye[1]) / 2)
    )

    # Matrice de rotation
    M = cv2.getRotationMatrix2D(eye_center, angle, scale=1.0)
    h_img, w_img = img_rgb.shape[:2]
    rotated = cv2.warpAffine(img_rgb, M, (w_img, h_img), flags=cv2.INTER_CUBIC)

    # Recadrer le visage avec marge
    pad = int(max(fw, fh) * 0.15)
    x1  = max(0, x - pad)
    y1  = max(0, y - pad)
    x2  = min(w_img, x + fw + pad)
    y2  = min(h_img, y + fh + pad)

    return rotated[y1:y2, x1:x2]


# ══════════════════════════════════════════════════════════════════
# PHASE 3 : ENCODAGE + COMPARAISON (FaceNet512 + Distance Cosine)
# ══════════════════════════════════════════════════════════════════

def _compare_faces(face_cin: np.ndarray, face_selfie: np.ndarray) -> dict:
    """
    Compare deux visages avec FaceNet512 et la distance cosine.

    FaceNet512 genere un vecteur de 512 dimensions (embedding) pour chaque visage.
    La distance cosine mesure l'angle entre les deux vecteurs.

    Seuil : distance < 0.40 = meme personne (calibre sur FaceNet512 + cosine)

    Avantage vs ArcFace seul :
      - FaceNet512 gere mieux le vieillissement (photo CIN ancienne vs selfie recent)
      - Cosine insensible aux variations de luminosite
    """
    from deepface import DeepFace

    result = DeepFace.verify(
        img1_path         = face_cin,        # numpy array 160x160 RGB
        img2_path         = face_selfie,     # numpy array 160x160 RGB
        model_name        = "Facenet512",
        detector_backend  = "skip",          # Detection deja faite par MTCNN
        distance_metric   = "cosine",
        enforce_detection = False,
    )

    distance         = result.get("distance", 1.0)
    verified         = distance < FACE_THRESHOLD
    # Convertir distance cosine en score de similarite comprehensible
    similarity_score = max(0.0, round(1.0 - distance, 4))

    return {
        "verified":         verified,
        "distance":         round(distance, 4),
        "similarity_score": similarity_score,
        "threshold":        FACE_THRESHOLD,
        "model":            "FaceNet512",
        "metric":           "cosine",
    }


# ══════════════════════════════════════════════════════════════════
# ENDPOINT 1 : POST /api/ai/face-extract-cin
# Etape 1 KYC : Extraire la photo du visage depuis la CIN
# ══════════════════════════════════════════════════════════════════

@router.post("/face-extract-cin")
async def face_extract_cin(
        cin_recto: UploadFile = File(..., description="Photo recto CIN tunisienne"),
        cin_verso: UploadFile = File(..., description="Photo verso CIN tunisienne")):
    """
    Etape 1 KYC Visiteur.
    Valide recto + verso CIN, extrait le visage (MTCNN, zone gauche).
    Retourne : face_base64 + verso_valide (a stocker en session Spring Boot).
    """
    t0 = time.time()

    try:
        recto_bytes = await cin_recto.read()
        verso_bytes = await cin_verso.read()

        # Validation recto
        img_recto = _decode_image(recto_bytes, "CIN recto")

        # Validation verso — doit etre une image lisible de resolution suffisante
        img_verso = _decode_image(verso_bytes, "CIN verso")
        verso_h, verso_w = img_verso.shape[:2]

        # Extraction visage depuis le recto (zone gauche CIN tunisienne)
        face_cin = _extract_face_mtcnn(img_recto, "CIN", zone_gauche_only=True)

        # Encoder le visage en Base64
        _, buf   = cv2.imencode(".jpg", face_cin, [cv2.IMWRITE_JPEG_QUALITY, 95])
        face_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        elapsed = round(time.time() - t0, 2)
        logger.info(f"face-extract-cin : recto+verso valides, visage extrait en {elapsed}s")

        return {
            "face_detected":  True,
            "face_base64":    face_b64,
            "verso_valide":   True,
            "verso_resolution": f"{verso_w}x{verso_h}",
            "processing_ms":  int(elapsed * 1000),
            "message":        "Recto et verso CIN valides. Visage extrait avec succes.",
        }

    except ValueError as e:
        logger.warning(f"face-extract-cin validation : {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"face-extract-cin erreur : {e}")
        raise HTTPException(status_code=500, detail=f"Erreur extraction visage : {str(e)[:200]}")


# ══════════════════════════════════════════════════════════════════
# ENDPOINT 2 : POST /api/ai/face-compare
# Etape 2 KYC : Comparer selfie avec visage extrait de la CIN
# ══════════════════════════════════════════════════════════════════

@router.post("/face-compare")
async def face_compare(
        selfie:      UploadFile = File(..., description="Selfie du visiteur"),
        face_base64: str        = Form(..., description="Photo visage CIN en Base64")):
    """
    Etape 2 KYC Visiteur.
    Compare le selfie avec la photo visage de la CIN.
    Utilise FaceNet512 + MTCNN + distance cosine.
    Seuil : distance < 0.40 → meme personne.
    """
    t0 = time.time()

    try:
        selfie_bytes = await selfie.read()

        # Phase 1 : Decodage
        img_selfie  = _decode_image(selfie_bytes, "Selfie")
        cin_bytes   = base64.b64decode(face_base64)
        arr_cin     = np.frombuffer(cin_bytes, np.uint8)
        img_cin_face = cv2.imdecode(arr_cin, cv2.IMREAD_COLOR)

        if img_cin_face is None:
            raise ValueError("Photo visage CIN (Base64) illisible")

        # Phase 2 : Detection + alignement du selfie (image complete)
        face_selfie = _extract_face_mtcnn(img_selfie, "Selfie", zone_gauche_only=False)

        # La face CIN est deja extraite (160x160) — pas besoin de re-detecter
        # Juste normaliser si besoin
        if img_cin_face.shape[:2] != (160, 160):
            img_cin_face = cv2.resize(img_cin_face, (160, 160))

        # Phase 3 : Comparaison FaceNet512 + cosine
        comparison = _compare_faces(img_cin_face, face_selfie)

        elapsed = round(time.time() - t0, 2)
        comparison["processing_ms"] = int(elapsed * 1000)

        # Phase 4 : Message comprehensible
        pct = int(comparison["similarity_score"] * 100)
        if comparison["verified"]:
            comparison["message"] = f"Identite confirmee — Correspondance : {pct}%"
        else:
            comparison["message"] = (
                f"Identite non confirmee — Correspondance : {pct}% "
                f"(seuil minimum : {int((1-FACE_THRESHOLD)*100)}%). "
                "Assurez-vous d'un bon eclairage et regardez directement la camera."
            )

        logger.info(
            f"face-compare : distance={comparison['distance']} "
            f"score={comparison['similarity_score']} "
            f"verified={comparison['verified']} "
            f"temps={elapsed}s"
        )

        return comparison

    except ValueError as e:
        logger.warning(f"face-compare validation : {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"face-compare erreur : {e}")
        return {
            "verified":         False,
            "similarity_score": 0.0,
            "distance":         1.0,
            "error":            str(e)[:300],
            "message":          "Erreur technique lors de la comparaison."
        }


# ══════════════════════════════════════════════════════════════════
# ENDPOINT 3 : POST /api/ai/cin-verify-number
# OCR du numero CIN depuis le recto, comparaison avec le numero saisi
# ══════════════════════════════════════════════════════════════════

def _fix_exif_rotation(raw_bytes: bytes) -> bytes:
    """Corrige la rotation EXIF avant decodage OpenCV (Android stocke en portrait avec tag EXIF)."""
    try:
        from PIL import Image, ExifTags
        import io as _io
        pil_img = Image.open(_io.BytesIO(raw_bytes))
        exif_data = pil_img._getexif()
        if exif_data:
            orientation_key = next(
                (k for k, v in ExifTags.TAGS.items() if v == "Orientation"), None
            )
            if orientation_key and orientation_key in exif_data:
                orientation = exif_data[orientation_key]
                if orientation == 3:
                    pil_img = pil_img.rotate(180, expand=True)
                elif orientation == 6:
                    pil_img = pil_img.rotate(270, expand=True)
                elif orientation == 8:
                    pil_img = pil_img.rotate(90, expand=True)
        buf = _io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception:
        return raw_bytes


# Singleton PaddleOCR pour extraction CIN (initialise a la premiere utilisation)
_paddle_cin: object = None

def _get_paddle_cin():
    global _paddle_cin
    if _paddle_cin is None:
        from paddleocr import PaddleOCR
        _paddle_cin = PaddleOCR(use_angle_cls=True, lang='en', show_log=False)
    return _paddle_cin


def _extract_cin_number(img_bgr: np.ndarray) -> tuple[str, float]:
    """
    Extrait le numero CIN (8 chiffres) via PaddleOCR.
    PaddleOCR detecte les zones de texte avec deep learning —
    ignore le watermark et lit correctement les gros chiffres latins.
    Fallback pytesseract si PaddleOCR ne trouve rien.
    """
    h, w = img_bgr.shape[:2]
    if h > w:
        img_bgr = cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
        h, w = img_bgr.shape[:2]

    # ── Tentative 1 : PaddleOCR ─────────────────────────────────────────────
    try:
        ocr     = _get_paddle_cin()
        results = ocr.ocr(img_bgr, cls=True)
        if results and results[0]:
            for line in results[0]:
                text  = line[1][0]
                conf  = float(line[1][1])
                digits = re.sub(r"\D", "", text)
                m = re.search(r"\d{8}", digits)
                if m:
                    logger.info(f"cin-extract PaddleOCR found={m.group(0)!r} conf={conf:.2f} text={text!r}")
                    return m.group(0), min(0.90, conf)
    except Exception as e:
        logger.warning(f"cin-extract PaddleOCR erreur: {e}")

    # ── Fallback : pytesseract sur zone ciblee ───────────────────────────────
    if not HAS_TESSERACT:
        return "", 0.0

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    y1 = int(h * 0.18); y2 = int(h * 0.50)
    x1 = int(w * 0.20); x2 = int(w * 0.85)
    crop = gray[y1:y2, x1:x2]
    if crop.size == 0:
        return "", 0.0

    scaled  = cv2.resize(crop, (crop.shape[1] * 3, crop.shape[0] * 3), interpolation=cv2.INTER_CUBIC)
    blurred = cv2.GaussianBlur(scaled, (5, 5), 0)
    _, bimg = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    for cfg in ["--psm 7 --oem 1 -c tessedit_char_whitelist=0123456789",
                "--psm 6 --oem 1 -c tessedit_char_whitelist=0123456789"]:
        try:
            raw    = pytesseract.image_to_string(bimg, config=cfg).strip()
            digits = re.sub(r"\D", "", raw)
            m = re.search(r"\d{8}", digits)
            if m:
                logger.info(f"cin-extract tesseract fallback found={m.group(0)!r}")
                return m.group(0), 0.70
        except Exception:
            continue

    return "", 0.0


@router.post("/cin-verify-number")
async def cin_verify_number(
    cin_recto:    UploadFile = File(..., description="Photo recto CIN tunisienne"),
    declared_cin: str        = Form(..., description="Numero CIN declare (8 chiffres)"),
):
    """
    OCR du numero CIN depuis le recto.
    Compare avec le numero saisi par l'utilisateur dans le formulaire.

    Retourne :
      - extracted_cin : numero lu par OCR
      - match         : true si identique au numero declare
      - confidence    : score OCR (0.0 - 1.0)
      - ocr_available : false si pytesseract non installe
    """
    if not HAS_TESSERACT:
        return {
            "ocr_available":  False,
            "extracted_cin":  None,
            "declared_cin":   declared_cin,
            "match":          None,
            "confidence":     0.0,
            "message":        "OCR non disponible sur ce serveur. Verification ignoree.",
        }

    t0 = time.time()
    try:
        recto_bytes = await cin_recto.read()
        recto_bytes = _fix_exif_rotation(recto_bytes)
        arr = np.frombuffer(recto_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            raise ValueError("Image CIN recto illisible")

        extracted, confidence = _extract_cin_number(img)

        # Normaliser : garder uniquement les chiffres pour la comparaison
        declared_clean  = re.sub(r"\D", "", declared_cin.strip())
        extracted_clean = re.sub(r"\D", "", extracted)

        match = bool(extracted_clean and extracted_clean == declared_clean)

        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            f"cin-verify-number : extracted={extracted_clean!r} "
            f"declared={declared_clean!r} match={match} conf={confidence:.2f} "
            f"ms={elapsed_ms}"
        )

        return {
            "ocr_available":  True,
            "extracted_cin":  extracted_clean or None,
            "declared_cin":   declared_clean,
            "match":          match,
            "confidence":     round(confidence, 2),
            "processing_ms":  elapsed_ms,
            "message": (
                "Numéro CIN vérifié et conforme." if match
                else f"Numéro CIN ne correspond pas (lu : {extracted_clean or 'non lisible'})."
            ),
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"cin-verify-number erreur : {e}")
        return {
            "ocr_available":  True,
            "extracted_cin":  None,
            "declared_cin":   declared_cin,
            "match":          None,
            "confidence":     0.0,
            "message":        f"Erreur OCR : {str(e)[:200]}",
        }
