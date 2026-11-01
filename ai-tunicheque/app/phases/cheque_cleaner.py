"""
app/phases/cheque_cleaner.py
============================
Boîte à outils OCR avancée pour chèques tunisiens — 5 techniques :

  1. NETTOYAGE MORPHOLOGIQUE  — Supprime les lignes pointillées imprimées,
                                ne garde que l'écriture manuscrite.

  2. ANCRAGE PAR MOT-CLÉ     — Cherche "ORDRE", "Le", "À" dans l'image,
                                extrait la zone à droite du mot trouvé.
                                Robuste aux photos de travers.

  3. EASYOCR                  — Moteur OCR deep learning, meilleur que
                                Tesseract sur le manuscrit français/arabe.

  4. CORRECTION RAPIDFUZZ     — Corrige les villes tunisiennes mal lues
                                (ex: "Tuni5" → "Tunis" à 95%).

  5. CMC7 / BANDE MAGNÉTIQUE  — Lit la ligne du bas (chiffres normalisés),
                                extrait code banque + code agence, fait un
                                lookup dans agences_tn.json → nom de l'agence.

Usage :
    from app.phases.cheque_cleaner import (
        enlever_lignes,
        ancrer_et_extraire,
        lire_easyocr,
        corriger_ville,
        extraire_date_du_texte,
        lire_ligne_cmc7,
        lookup_agence,
    )
"""

import re
import cv2
import json
import numpy as np
from pathlib import Path
from typing import Optional, Dict

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logger = logging.getLogger("cheque_cleaner")

# ── Chemin vers la table d'agences ───────────────────────────────────────────
_DATA_DIR     = Path(__file__).parent.parent / "data"
_AGENCES_PATH = _DATA_DIR / "agences_tn.json"

# ── Codes banques BCT officiels (23 banques + La Poste) ──────────────────────
RIB_BANK_MAP = {
    "01": "ATB",          # Arab Tunisian Bank
    "03": "BNA",          # Banque Nationale Agricole
    "04": "Attijari Bank",# Attijari Bank Tunisie (ex Banque du Sud)
    "05": "BT",           # Banque de Tunisie
    "07": "Amen Bank",    # Amen Bank (ex Crédit Foncier)
    "08": "BIAT",         # Banque Internationale Arabe de Tunisie
    "10": "STB",          # Société Tunisienne de Banque
    "11": "UBCI",         # Union Bancaire pour le Commerce et l'Industrie
    "12": "UIB",          # Union Internationale de Banques
    "14": "BH Bank",      # BH Bank (Banque de l'Habitat)
    "17": "La Poste",     # La Poste Tunisienne
    "20": "BTK",          # Banque Tuniso-Koweïtienne
    "21": "Citibank",     # Citibank Tunisie
    "23": "ABC",          # Arab Banking Corporation Tunisie
    "24": "Stusid Bank",  # Stusid Bank
    "25": "Zitouna Bank", # Zitouna Bank
    "26": "QNB",          # QNB Tunisie (Qatar National Bank)
    "31": "BTS",          # Banque Tunisienne de Solidarité
    "32": "Al Baraka",    # Al Baraka Bank Tunisie
    "33": "BFPME",        # Banque de Financement des PME
    "34": "El Wifack",    # El Wifack Bank
    "60": "BTE",          # Banque de Tunisie et des Emirats
    "64": "NAIB",         # North Africa International Bank
}

# ── Table d'agences (chargée une seule fois) ──────────────────────────────────
_AGENCES: Optional[Dict] = None

def _charger_agences() -> Dict:
    global _AGENCES
    if _AGENCES is None:
        if _AGENCES_PATH.exists():
            try:
                with open(_AGENCES_PATH, encoding="utf-8") as f:
                    _AGENCES = json.load(f)
            except Exception as e:
                logger.warning("agences_chargement_erreur", error=str(e))
                _AGENCES = {}
        else:
            _AGENCES = {}
    return _AGENCES


# ── Villes tunisiennes pour correction rapidfuzz ──────────────────────────────
VILLES_TUNISIE = [
    "Tunis", "Sfax", "Sousse", "Kairouan", "Bizerte", "Gabès", "Gafsa",
    "Monastir", "Médenine", "Nabeul", "Tataouine", "Béja", "Kef", "Mahdia",
    "Sidi Bouzid", "Siliana", "Tozeur", "Zaghouan", "Manouba", "Ariana",
    "Ben Arous", "Kasserine",
    # Quartiers / agglomérations fréquents sur chèques
    "La Marsa", "Carthage", "Lac 2", "Centre Urbain Nord", "Ennasr",
    "El Menzah", "La Soukra", "Rades", "Hammam-Lif", "Berges du Lac",
    "Kheireddine", "Megrine", "Borj Cedria", "El Aouina",
    "Hammam Sousse", "Akouda", "Msaken", "Kalaa Kebira",
    "Sfax Centre", "Sfax Sud", "Chebba",
]


# ══════════════════════════════════════════════════════════════════════════════
#  1. NETTOYAGE MORPHOLOGIQUE — Suppression des lignes pointillées
# ══════════════════════════════════════════════════════════════════════════════

def enlever_lignes(img_bgr: np.ndarray,
                   longueur_min: int = 30) -> np.ndarray:
    """
    Supprime les lignes imprimées (pointillés, tirets, traits continus)
    en utilisant la morphologie mathématique OpenCV.

    Principe :
      1. Binariser l'image (texte noir sur fond blanc)
      2. Kernel horizontal très fin → détecter les lignes longues
      3. Soustraire les lignes → il reste le texte manuscrit "flottant"

    Paramètres :
      img_bgr      : image BGR du crop
      longueur_min : longueur minimale d'une ligne détectée (pixels)

    Retourne :
      image BGR nettoyée (mêmes dimensions que l'entrée)
    """
    if img_bgr is None or img_bgr.size == 0:
        return img_bgr

    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Binarisation Otsu (texte = 255, fond = 0)
    _, thresh = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # ── Détecter les lignes horizontales ──────────────────────────────────
    # Kernel fin et long → ouvre uniquement les traits horizontaux longs
    kernel_h = cv2.getStructuringElement(
        cv2.MORPH_RECT, (longueur_min, 1))
    lignes_h = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel_h)

    # Dilater légèrement pour couvrir les pointillés espacés
    kernel_d = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 1))
    lignes_h = cv2.dilate(lignes_h, kernel_d, iterations=1)

    # ── Soustraire les lignes de l'image binarisée ────────────────────────
    propre = cv2.subtract(thresh, lignes_h)

    # Reconvertir en BGR (fond blanc, texte noir)
    propre_bgr = cv2.cvtColor(cv2.bitwise_not(propre), cv2.COLOR_GRAY2BGR)

    logger.debug("lignes_supprimees",
                 pixels_supprimes=int(np.sum(lignes_h > 0)))
    return propre_bgr


# ══════════════════════════════════════════════════════════════════════════════
#  2. EASYOCR — Moteur deep learning, meilleur sur le manuscrit
# ══════════════════════════════════════════════════════════════════════════════

_easyocr_reader = None

def _get_easyocr():
    """Singleton EasyOCR (chargé une seule fois — modèle lourd)."""
    global _easyocr_reader
    if _easyocr_reader is None:
        try:
            import easyocr
            _easyocr_reader = easyocr.Reader(
                ['fr', 'ar'],
                gpu=False,
                verbose=False,
            )
            logger.info("easyocr_charge", langues="fr+ar")
        except ImportError:
            logger.warning(
                "easyocr_absent",
                solution="pip install easyocr"
            )
        except Exception as e:
            logger.error("easyocr_init_erreur", error=str(e))
    return _easyocr_reader


def lire_easyocr(crop: np.ndarray,
                 chiffres_seulement: bool = False) -> str:
    """
    Lance EasyOCR sur un crop, retourne le texte concaténé.

    Paramètres :
      crop              : image numpy BGR
      chiffres_seulement: si True, n'accepte que 0-9 (pour CMC7)
    """
    reader = _get_easyocr()
    if reader is None or crop is None or crop.size == 0:
        return ""
    try:
        allowlist = "0123456789" if chiffres_seulement else None
        kwargs    = {"allowlist": allowlist} if allowlist else {}
        resultats = reader.readtext(crop, **kwargs)
        # Trier par position horizontale (gauche → droite)
        resultats.sort(key=lambda r: r[0][0][0])
        mots = [r[1] for r in resultats if r[2] > 0.3]
        return " ".join(mots).strip()
    except Exception as e:
        logger.error("easyocr_lecture_erreur", error=str(e))
        return ""


# ══════════════════════════════════════════════════════════════════════════════
#  3. ANCRAGE PAR MOT-CLÉ
# ══════════════════════════════════════════════════════════════════════════════

def ancrer_et_extraire(img_bgr: np.ndarray,
                       mot_cle: str,
                       largeur: int  = 350,
                       hauteur: int  = 55,
                       offset_x: int = 12) -> Optional[np.ndarray]:
    """
    Trouve le mot-clé imprimé dans l'image (via EasyOCR),
    puis extrait la zone manuscrite à sa droite.

    Mots-clés utiles sur un chèque tunisien :
      "ORDRE"   → zone bénéficiaire
      "Le"      → zone date d'émission
      "À"       → zone lieu (ville)
      "Somme"   → zone montant lettres
      "Payez"   → zone montant chiffres

    Paramètres :
      img_bgr  : image complète du chèque
      mot_cle  : texte à chercher (case-insensitive)
      largeur  : largeur de la zone à extraire (pixels)
      hauteur  : hauteur de la zone à extraire (pixels)
      offset_x : marge entre la fin du mot-clé et le début du crop

    Retourne :
      crop BGR de la zone trouvée, ou None si le mot-clé est absent.
    """
    reader = _get_easyocr()
    if reader is None or img_bgr is None:
        return None

    h_img, w_img = img_bgr.shape[:2]

    try:
        resultats = reader.readtext(img_bgr)
    except Exception as e:
        logger.error("ancrage_ocr_erreur", error=str(e))
        return None

    for (bbox, texte, conf) in resultats:
        if mot_cle.upper() in texte.upper() and conf > 0.25:
            # bbox = [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            x_droite = max(p[0] for p in bbox)
            y_centre = sum(p[1] for p in bbox) / len(bbox)

            x1 = int(x_droite) + offset_x
            y1 = max(0,     int(y_centre - hauteur // 2))
            x2 = min(w_img, x1 + largeur)
            y2 = min(h_img, int(y_centre + hauteur // 2))

            if x1 >= x2 or y1 >= y2:
                continue

            crop = img_bgr[y1:y2, x1:x2]
            if crop.size > 0:
                logger.debug("ancrage_trouve",
                             mot=mot_cle, conf=round(conf, 2),
                             zone=(x1, y1, x2, y2))
                return crop

    logger.debug("ancrage_absent", mot=mot_cle)
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  4. CORRECTION RAPIDFUZZ — Villes tunisiennes
# ══════════════════════════════════════════════════════════════════════════════

def corriger_ville(texte: str, seuil: int = 70) -> str:
    """
    Corrige un nom de ville mal lu par OCR via fuzzy matching.

    Exemples :
      "Tuni5"    → "Tunis"    (95%)
      "Souss"    → "Sousse"   (88%)
      "La Mars"  → "La Marsa" (92%)
      "0" / ""   → inchangé

    Paramètres :
      texte : texte OCR brut
      seuil : score minimum pour accepter la correction (0-100)
    """
    if not texte or len(texte.strip()) < 2:
        return texte

    mot = texte.strip()

    try:
        from rapidfuzz import process, fuzz
        res = process.extractOne(mot, VILLES_TUNISIE, scorer=fuzz.WRatio)
        if res and res[1] >= seuil:
            logger.debug("ville_corrigee",
                         brut=mot, corrige=res[0], score=res[1])
            return res[0]
    except ImportError:
        from difflib import get_close_matches
        m = get_close_matches(mot, VILLES_TUNISIE, n=1, cutoff=0.65)
        if m:
            return m[0]
    except Exception as e:
        logger.debug("corriger_ville_erreur", error=str(e))

    return texte


# ══════════════════════════════════════════════════════════════════════════════
#  DATE — Extraction et correction
# ══════════════════════════════════════════════════════════════════════════════

def extraire_date_du_texte(texte: str) -> Optional[str]:
    """
    Extrait une date au format JJ/MM/AAAA depuis un texte OCR.

    Formats reconnus :
      "15/03/2025"   → "15/03/2025"
      "15-03-2025"   → "15/03/2025"
      "15.03.2025"   → "15/03/2025"
      "15/03/25"     → "15/03/2025"
      "15032025"     → "15/03/2025"
    """
    if not texte:
        return None

    t = texte.strip()

    patterns = [
        # DD/MM/YYYY ou DD-MM-YYYY ou DD.MM.YYYY
        r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{4})\b',
        # DD/MM/YY (2 chiffres pour l'année)
        r'\b(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2})\b',
        # DDMMYYYY (compact, 8 chiffres)
        r'\b(\d{2})(\d{2})(\d{4})\b',
    ]

    for pat in patterns:
        m = re.search(pat, t)
        if m:
            j, mo, a = m.group(1), m.group(2), m.group(3)
            if len(a) == 2:
                a = "20" + a
            try:
                from datetime import datetime
                d = datetime(int(a), int(mo), int(j))
                # Vérifier cohérence (pas de date future > 1 an)
                from datetime import date
                if d.date() <= date.today().replace(year=date.today().year + 1):
                    return d.strftime("%d/%m/%Y")
            except ValueError:
                pass

    return None


# ══════════════════════════════════════════════════════════════════════════════
#  5. CMC7 — Ligne magnétique du bas du chèque
# ══════════════════════════════════════════════════════════════════════════════

def lire_ligne_cmc7(img_bgr: np.ndarray,
                    hauteur_pct: float = 0.18) -> Optional[str]:
    """
    Extrait la bande CMC7 (bas du chèque) et lit les chiffres avec EasyOCR.

    La police CMC7/E13B est standardisée → très haute précision OCR.

    Paramètres :
      img_bgr     : image complète du chèque
      hauteur_pct : fraction de l'image à prendre (défaut: 18% du bas)

    Retourne :
      Chaîne de chiffres uniquement (ex: "10001000000000000197012345799"),
      ou None si aucun chiffre extrait.
    """
    if img_bgr is None or img_bgr.size == 0:
        return None

    h, w = img_bgr.shape[:2]
    y_debut = int(h * (1.0 - hauteur_pct))
    bande   = img_bgr[y_debut:h, :]

    # Prétraitement : contraste + binarisation pour CMC7
    gray   = cv2.cvtColor(bande, cv2.COLOR_BGR2GRAY)
    _, bw  = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    bande_prep = cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)

    # EasyOCR en mode chiffres seulement
    texte   = lire_easyocr(bande_prep, chiffres_seulement=True)
    chiffres = re.sub(r'[^\d]', '', texte)

    if chiffres:
        logger.info("cmc7_lu", longueur=len(chiffres), debut=chiffres[:8])
        return chiffres

    logger.debug("cmc7_vide")
    return None


def parser_cmc7(chiffres: str) -> Dict:
    """
    Parse les chiffres CMC7 selon le format BCT tunisien.

    Format (28 chiffres) :
      [0:2]   code_banque  (2) — ex: "08" = BIAT
      [2:5]   code_agence  (3) — ex: "048" = Agence Lac 2
      [5:18]  num_compte   (13)
      [18:25] num_cheque   (7)
      [25:27] cle          (2)

    Retourne un dict avec les champs parsés.
    """
    if not chiffres or len(chiffres) < 20:
        return {}

    # Nettoyer
    c = re.sub(r'[^\d]', '', chiffres)

    result = {}
    if len(c) >= 2:  result["code_banque"] = c[0:2]
    if len(c) >= 5:  result["code_agence"] = c[2:5]
    if len(c) >= 18: result["num_compte"]  = c[5:18]
    if len(c) >= 25: result["num_cheque"]  = c[18:25]
    if len(c) >= 27: result["cle"]         = c[25:27]

    # Reconstruire le RIB (code_banque + code_agence + num_compte + clé_rib)
    if len(c) >= 18:
        rib_base = c[0:18]
        from app.phases.phase2_ocr_yolo import _luhn_rib
        try:
            # Calculer la clé RIB correcte
            reste   = int(rib_base) * 100 % 97
            cle_rib = str(97 - reste).zfill(2)
            rib_complet = rib_base + cle_rib
            if _luhn_rib(rib_complet):
                result["rib"] = rib_complet
        except Exception:
            pass

    logger.debug("cmc7_parse", **result)
    return result


def lookup_agence(code_banque: str, code_agence: str) -> str:
    """
    Retourne le nom de l'agence bancaire à partir des codes CMC7.

    Cherche dans agences_tn.json (clé = "BB_AAA").
    Fallback : "Agence AAA (NOM_BANQUE)".

    Exemples :
      lookup_agence("08", "025") → "BIAT — Agence Lac 2"
      lookup_agence("03", "048") → "BNA — Agence Carthage"
      lookup_agence("99", "999") → "Agence 999 (Banque inconnue)"
    """
    agences = _charger_agences()
    cle     = f"{code_banque}_{code_agence}"

    if cle in agences:
        return agences[cle]

    nom_banque = RIB_BANK_MAP.get(code_banque, "Banque inconnue")
    return f"{nom_banque} — Agence {code_agence}"


# ══════════════════════════════════════════════════════════════════════════════
#  PIPELINE COMPLET — Extraire les 4 champs via ancrage
# ══════════════════════════════════════════════════════════════════════════════

def extraire_champs_par_ancrage(img_bgr: np.ndarray) -> Dict:
    """
    Extrait bénéficiaire, date, lieu et agence depuis une image de chèque
    en utilisant uniquement l'ancrage par mots-clés + EasyOCR.

    Méthode sans YOLO — robuste aux photos de travers.

    Retourne :
    {
      "beneficiaire" : str | None,
      "date"         : str | None,   # format DD/MM/YYYY
      "lieu"         : str | None,   # ville corrigée
      "agence"       : str | None,   # depuis CMC7
      "tireur_rib"   : str | None,   # RIB depuis CMC7
      "methode"      : "ancrage"
    }
    """
    result = {
        "beneficiaire": None,
        "date":         None,
        "lieu":         None,
        "agence":       None,
        "tireur_rib":   None,
        "methode":      "ancrage",
    }

    if img_bgr is None or img_bgr.size == 0:
        return result

    # ── 1. Nettoyage des lignes imprimées ────────────────────────────────
    img_propre = enlever_lignes(img_bgr)

    # ── 2. Bénéficiaire — ancrage sur "ORDRE" ───────────────────────────
    crop_benef = ancrer_et_extraire(img_propre, "ORDRE",
                                    largeur=400, hauteur=60)
    if crop_benef is not None:
        texte_b = lire_easyocr(crop_benef)
        if texte_b:
            result["beneficiaire"] = texte_b.strip()
            logger.info("beneficiaire_ancrage", valeur=result["beneficiaire"])

    # ── 3. Date — ancrage sur "Le" ───────────────────────────────────────
    crop_date = ancrer_et_extraire(img_propre, "Le",
                                   largeur=200, hauteur=50)
    if crop_date is not None:
        texte_d = lire_easyocr(crop_date)
        result["date"] = extraire_date_du_texte(texte_d)
        logger.info("date_ancrage", brut=texte_d, date=result["date"])

    # ── 4. Lieu — ancrage sur "À" (même ligne que la date) ───────────────
    crop_lieu = ancrer_et_extraire(img_propre, "À",
                                   largeur=200, hauteur=50)
    if crop_lieu is None:
        crop_lieu = ancrer_et_extraire(img_propre, "A ",
                                       largeur=200, hauteur=50)
    if crop_lieu is not None:
        texte_l = lire_easyocr(crop_lieu)
        if texte_l:
            result["lieu"] = corriger_ville(texte_l.strip())
            logger.info("lieu_ancrage",
                        brut=texte_l, corrige=result["lieu"])

    # ── 5. CMC7 — bande du bas → agence + RIB ────────────────────────────
    chiffres_cmc7 = lire_ligne_cmc7(img_bgr)
    if chiffres_cmc7:
        parsed = parser_cmc7(chiffres_cmc7)
        if "code_banque" in parsed and "code_agence" in parsed:
            result["agence"] = lookup_agence(
                parsed["code_banque"], parsed["code_agence"])
        if "rib" in parsed:
            result["tireur_rib"] = parsed["rib"]
        logger.info("cmc7_ancrage",
                    agence=result["agence"], rib=result["tireur_rib"])

    return result
