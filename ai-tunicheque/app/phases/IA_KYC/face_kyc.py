"""
app/face_kyc.py — Moteur KYC Biometrique
==========================================
Face verification CIN tunisienne vs Selfie.
MTCNN (detection) + FaceNet512 (embeddings) + Cosine (comparaison).
PAS d'OCR — comparaison biometrique pure.

Installer :
    pip install deepface mtcnn tensorflow opencv-python Pillow

AJOUTER dans app/main.py :
    from app.face_kyc import router as kyc_router
    app.include_router(kyc_router)
"""

import cv2
import base64
import logging
import time
import numpy as np
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from typing import Optional

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["KYC Biometrique"])

# ══════════════════════════════════════════════════════════════════
# PARAMETRES GLOBAUX
# ══════════════════════════════════════════════════════════════════
FACE_THRESHOLD   = 0.45   # Distance cosine max = meme personne (FaceNet512)
                          # 0.45 → seuil 55% similarite min (tolere vieillissement + conditions variables)
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
    Pour la CIN : cherche dans la zone gauche 40% (photo du titulaire).
                  Si echoue, retry sur l'image complete (CIN mal cadree).
                  Aucun fallback zone fixe — rejette si vraiment pas de visage.
    Pour le selfie : cherche sur toute l'image.
    """
    from mtcnn import MTCNN
    detector = MTCNN()

    def _detect_in(region_bgr: np.ndarray):
        rgb = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2RGB)
        return detector.detect_faces(rgb), rgb

    if zone_gauche_only:
        h, w = img_bgr.shape[:2]
        zone = img_bgr[:, :int(w * CIN_FACE_ZONE)]
        results, img_rgb = _detect_in(zone)

        if not results:
            # Retry sur l'image complete (CIN mal cadree ou legerement inclinee)
            logger.warning(f"MTCNN zone gauche echouee sur {label} — retry image complete")
            results, img_rgb = _detect_in(img_bgr)

        if not results:
            raise ValueError(
                "Aucun visage detecte sur la CIN. "
                "Verifiez que c'est bien le RECTO (face avec photo), "
                "bien eclaire et dans le cadre."
            )
    else:
        results, img_rgb = _detect_in(img_bgr)
        if not results:
            raise ValueError(
                f"Aucun visage detecte sur le selfie ({label}). "
                "Assurez-vous d'etre bien eclaire et de regarder la camera."
            )

    # Prendre le visage avec la meilleure confiance
    best = max(results, key=lambda r: r["confidence"])

    if best["confidence"] < 0.80:
        logger.warning(f"Confiance faible sur {label} : {best['confidence']:.2f}")

    x, y, fw, fh = best["box"]
    face_img = _align_face(img_rgb, x, y, fw, fh, best["keypoints"])
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

def _clahe_normalize(face_rgb: np.ndarray) -> np.ndarray:
    """
    Normalisation adaptative CLAHE (Contrast Limited Adaptive Histogram Equalization).
    Egalise la luminosite et le contraste independamment pour chaque image.
    Compense : eclairage different CIN studio vs selfie naturel, vieillissement,
               contre-jour, reflets lunettes.
    """
    face_lab = cv2.cvtColor(face_rgb, cv2.COLOR_RGB2LAB)
    l, a, b  = cv2.split(face_lab)
    clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    l_eq     = clahe.apply(l)
    enhanced = cv2.merge([l_eq, a, b])
    return cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)


def _compare_faces(face_cin: np.ndarray, face_selfie: np.ndarray) -> dict:
    """
    Compare deux visages avec FaceNet512 et la distance cosine.
    Applique CLAHE sur les deux images avant comparaison pour normaliser
    les differences d'eclairage (CIN photo studio vs selfie conditions variables).

    Seuil : distance < 0.45 (similarite min 55%) — tolere vieillissement + eclairage variable.
    """
    from deepface import DeepFace

    # Normalisation CLAHE — recupère 10-20 pts de similarite sur photos anciennes
    face_cin_n    = _clahe_normalize(face_cin)
    face_selfie_n = _clahe_normalize(face_selfie)

    result = DeepFace.verify(
        img1_path         = face_cin_n,
        img2_path         = face_selfie_n,
        model_name        = "Facenet512",
        detector_backend  = "skip",
        distance_metric   = "cosine",
        enforce_detection = False,
    )

    distance         = result.get("distance", 1.0)
    verified         = distance < FACE_THRESHOLD
    similarity_score = max(0.0, round(1.0 - distance, 4))

    return {
        "verified":         verified,
        "distance":         round(distance, 4),
        "similarity_score": similarity_score,
        "threshold":        FACE_THRESHOLD,
        "model":            "FaceNet512+CLAHE",
        "metric":           "cosine",
    }


# ══════════════════════════════════════════════════════════════════
# ENDPOINT 1 : POST /api/ai/face-extract-cin
# Etape 1 KYC : Extraire la photo du visage depuis la CIN
# ══════════════════════════════════════════════════════════════════

@router.post("/face-extract-cin")
async def face_extract_cin(
        cin_recto: UploadFile = File(..., description="Photo recto CIN tunisienne")):
    """
    Etape 1 KYC Visiteur.
    Extrait le visage de la photo CIN (MTCNN, zone gauche).
    Retourne : face_base64 (a stocker en session Spring Boot).
    """
    t0 = time.time()

    try:
        recto_bytes = await cin_recto.read()

        # Phase 1 : Decodage + validation
        img = _decode_image(recto_bytes, "CIN recto")

        # Phase 2 : Detection + alignement (zone gauche CIN tunisienne)
        face_cin = _extract_face_mtcnn(img, "CIN", zone_gauche_only=True)

        # Encoder en Base64 pour retourner a Spring Boot
        img_rgb  = cv2.cvtColor(face_cin, cv2.COLOR_BGR2RGB) if len(face_cin.shape) == 3 else face_cin
        _, buf   = cv2.imencode(".jpg", face_cin, [cv2.IMWRITE_JPEG_QUALITY, 95])
        face_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        elapsed = round(time.time() - t0, 2)
        logger.info(f"face-extract-cin : visage extrait en {elapsed}s")

        return {
            "face_detected":  True,
            "face_base64":    face_b64,
            "processing_ms":  int(elapsed * 1000),
            "message":        "Visage extrait avec succes depuis la CIN.",
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
                "Conseils : eclairage face a vous, pas de contre-jour, "
                "regardez directement la camera, telechone tenu droit."
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
