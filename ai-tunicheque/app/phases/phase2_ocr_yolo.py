"""
app/phases/phase2_ocr_yolo.py
==============================
Moteur OCR Phase 2 — Architecture corrigee.

PHILOSOPHIE (senior) :
  Le QR pecc.tn est la SOURCE DE VERITE.
  Il est signe cryptographiquement par la BCT.
  On ne peut pas le falsifier sans invalider le hash.

  L'OCR sur le cheque physique sert UNIQUEMENT a detecter
  une falsification : quelqu'un a-t-il modifie le montant
  ecrit sur le papier APRES impression du QR ?

  DECISION CORRECTE :
    OCR non extrait          → WARN (pas FAIL) + agent verifie
    OCR = QR                 → pas de falsification
    OCR ≠ QR (diff > 1 DT)  → FALSIFICATION detectee

  JAMAIS de "Plafond = numero_cheque" par erreur de regex.

ARCHITECTURE :
  1. Avec YOLO : crop de la zone exacte → OCR ciblé → précis
  2. Sans YOLO : 4 passes PaddleOCR → regex stricte (sans fallback dangereux)
  3. Résultat enrichi par les données QR (toujours disponibles)

METHODE extraire() retourne :
  {
    "numero_cheque" : str  | None,
    "rib"           : str  | None,
    "date"          : str  | None,
    "montant"       : float| None,
    "confiance"     : float,
    "source_ocr"    : str,
    "ocr_disponible": bool,   ← True si au moins un champ extrait
  }
"""

import os, re, cv2
import numpy as np
from pathlib import Path
from typing import Optional

try:
    from app.phases.cheque_cleaner import (
        lire_ligne_cmc7,
        parser_cmc7,
        lookup_agence,
    )
    _CMC7_OK = True
except ImportError:
    _CMC7_OK = False

os.environ["FLAGS_use_mkldnn"]                      = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["GLOG_minloglevel"]                      = "3"

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

YOLO_CLASSES = {
    0: "montant_plafond",
    1: "numero_cheque",
    2: "rib_cmc7",
    3: "date",
    4: "beneficiaire",
    5: "montant_chiffres",
    6: "montant_lettres",
    7: "signature",
}

YOLO_DEFAULT_PATHS = [
    "saved_models/yolo_cheque/weights/best.pt",
    "saved_models/yolo_cheque/weights/last.pt",
    "best.pt",
]


# ══════════════════════════════════════════════════════════════════════════
#  EXTRACTION REGEX — STRICTE ET ROBUSTE
#
#  PRINCIPES :
#    1. Chaque champ a sa zone YOLO → crop court → regex simple
#    2. Sans YOLO : regex stricte avec contexte (pas de fallback numerique)
#    3. Jamais de \b(\d{4,})\b → trop dangeureux (capture n° cheque)
# ══════════════════════════════════════════════════════════════════════════

def _extraire_numero_cheque(texte: str) -> Optional[str]:
    """
    N° cheque : 6-8 chiffres AVEC contexte "cheque n°" ou seuls
    sur un crop cible YOLO.

    Sur un crop de zone numero_cheque, le texte est court :
    "Cheque n° 4122752" ou juste "4122752"
    → Pas de risque de confusion avec d'autres nombres.
    """
    # Avec contexte explicite (prioritaire)
    m = re.search(
        r'(?:ch[eè]que\s*[n°o]+\s*[:.]?\s*)(\d{6,8})',
        texte, re.IGNORECASE)
    if m: return m.group(1)

    # Seul (sur crop YOLO ciblé uniquement — fiable car crop petit)
    m = re.search(r'\b(\d{6,8})\b', texte)
    return m.group(1) if m else None


def _extraire_date(texte: str) -> Optional[str]:
    """
    Extraction de la date de validite du cheque.

    FORMATS REELS OBSERVES :
      "date d'expiration 20/03/2026 تاريخ انتهاء الصلوحية"
      "valable jusqu'a 27/03/2027"
      "Date expiration : 19/09/2025"
      "تاريخ انتهاء الصلوحية 15/06/2026"
      "Le 19/09/2025 a Tunis"
      "19092025"  (format compresse)
    """
    t = re.sub(r'\s+', ' ', texte.lower().strip())

    patterns = [
        # "date d'expiration 20/03/2026" ou "date expiration : 20/03/2026"
        r'date\s*(?:d\'?expir\w*|validit\w*)\s*:?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',

        # "valable jusqu'a 27/03/2027" ou "valable jusqu au 01/01/2027"
        r'valable\s*(?:jusqu\w*\s*[àa]?)?\s*[:\s]?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',

        # Arabe : تاريخ انتهاء الصلوحية suivi d'une date
        r'(?:تاريخ\s*انتهاء)[^0-9]{0,20}(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',

        # Date seule DD/MM/YYYY — format non ambigu
        r'\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b',

        # Date compressee DDMMYYYY (8 chiffres)
        r'\b(\d{8})\b',
    ]

    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            d = m.group(1)
            if len(d) == 8 and d.isdigit():
                return "{}/{}/{}".format(d[0:2], d[2:4], d[4:8])
            return d.replace('-', '/').replace('.', '/').strip()
    return None


def _luhn_rib(rib: str) -> bool:
    """
    Valide un RIB tunisien (20 chiffres) via la formule BCT :
      clé_contrôle (positions 18-19) = 97 − (int(rib[:18]) × 100) mod 97
    """
    if len(rib) != 20 or not rib.isdigit():
        return False
    try:
        cc = 97 - (int(rib[:18]) * 100) % 97
        return int(rib[18:20]) == cc
    except Exception:
        return False


def _extraire_rib(texte: str) -> Optional[str]:
    """
    Extraction du RIB (20 chiffres) avec validation Luhn BCT.

    ALGORITHME :
      1. Patterns contextuels (titulaire/rib/compte) → valider Luhn → retourner
      2. Toutes les séquences 20 chiffres → valider Luhn
      3. CMC7 (28 chiffres) → chars 8-27 = RIB → valider Luhn
      4. Fallback : première séquence 20 chiffres sans validation (OCR seul)

    Le CMC7 tunisien = {num_cheque 7ch}1{RIB 20ch} = 28 chiffres au total.
    """
    t_compact = re.sub(r'\s', '', texte)
    t         = texte.lower()

    contextual_patterns = [
        r'(?:titulaire\s*du\s*compte|صاحب\s*الحساب)[^0-9]{0,30}?(\d{20})',
        r'(?:rib|r\.i\.b\.?)\s*:?\s*(\d{20})',
        r'compte\s*n[o°]?\s*:?\s*(\d{20})',
    ]

    # Étape 1 : patterns contextuels + Luhn
    for pat in contextual_patterns:
        for src in [t_compact, t]:
            for m in re.finditer(pat, src, re.IGNORECASE):
                candidate = re.sub(r'\s', '', m.group(1))
                if _luhn_rib(candidate):
                    return candidate

    # Étape 2 : toutes les séquences de 20 chiffres — garder celle qui passe Luhn
    for src in [t_compact, t]:
        for m in re.finditer(r'\d{20}', src):
            candidate = m.group(0)
            if _luhn_rib(candidate):
                return candidate

    # Étape 3 : CMC7 (28 chiffres) → chars 8-27 = RIB
    for src in [t_compact, t]:
        for m in re.finditer(r'\d{28}', src):
            candidate = m.group(0)[8:28]
            if _luhn_rib(candidate):
                return candidate

    # Étape 4 : fallback sans Luhn (OCR imparfait)
    for src in [t_compact, t]:
        m = re.search(r'\d{20}', src)
        if m:
            return m.group(0)

    return None


def _extraire_montant_strict(texte: str) -> Optional[float]:
    """
    Extraction du plafond pour n'importe quel cheque tunisien.

    FORMATS REELS OBSERVES SUR LES CHEQUES TUNISIENS :
      "plafond du cheque : 5000dt"
      "Montant Max DT 5000 قيمة القصوى دت"
      "Montant max : 2000dt"
      "Valeur Maximal DT 5000 قيمة القصوى دت"
      "Montant max DT 10000 المبلغ الاقصى دت"

    REGLES :
      - Toujours exiger un mot-cle de contexte (plafond/montant/DT/arabe)
      - JAMAIS de \b(\d{4,})\b → capturerait le numero de cheque
      - Plafond max BCT = 30 000 DT → contrainte stricte

    MOTS-CLES :
      Francais : plafond, montant max, valeur maximal
      Arabe    : قيمة القصوى, المبلغ الاقصى
      Unites   : DT, dt, دت (colle ou separe)
    """
    # Normaliser : minuscules + reduire espaces
    t = texte.lower().strip()
    t = re.sub(r'\s+', ' ', t)

    patterns = [
        # "plafond du cheque : 5000dt", "PLAFOND DU CHEQUE 8000 DT"
        r'plafond[^0-9]{0,30}?(\d+(?:[,.]\d+)?)\s*d\.?t\.?',

        # "Montant max : 2000dt", "Montant Max DT 5000", "montant maximum : 15000"
        r'montant\s*max[a-z]*[^0-9]{0,20}?(\d+(?:[,.]\d+)?)',

        # "Valeur Maximal DT 5000", "valeur max: 25000dt"
        r'valeur\s*max[a-z]*[^0-9]{0,20}?(\d+(?:[,.]\d+)?)',

        # "DT 5000 ..." ou "dt5000" — DT avant le nombre
        r'd\.?t\.?\s*(\d+(?:[,.]\d+)?)',

        # "5000dt" ou "5000 DT" — DT apres, colle ou 1-3 espaces
        r'(\d+(?:[,.]\d+)?)\s{0,3}d\.?t\.?',

        # Arabe : "قيمة القصوى دت 5000" ou "المبلغ الاقصى دت"
        r'(?:قيمة\s*القصوى|المبلغ\s*الاقصى)[^0-9]{0,15}?(\d+(?:[,.]\d+)?)',
    ]

    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                raw = m.group(1).strip()
                # Couper le bruit apres le premier espace
                raw = raw.split()[0] if ' ' in raw else raw
                v   = float(re.sub(r'[\s]', '', raw).replace(',', '.'))
                # Plafond max BCT confirme : 30 000 DT
                if 10 <= v <= 30_000:
                    return v
            except ValueError:
                pass
    return None


def _clean_tireur_name(raw: str) -> Optional[str]:
    """
    Nettoie le nom tireur extrait :
    - Supprime les préfixes civils (MR., MME., DR., M.)
    - Garde uniquement les 2 premiers mots alphabétiques purs
      (lettres seulement, >= 2 chars) → exclut codes agence (AG, 23A, MAGHR...)
    - Retourne None si moins de 2 mots valides
    """
    prefixes = re.compile(
        r'^(?:MR\.?|MME\.?|MLLE\.?|DR\.?|M\.)\s*', re.IGNORECASE)
    raw = prefixes.sub('', raw.strip().upper())

    # Mots purement alphabétiques de >= 2 lettres
    words = re.findall(r'[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,}', raw)

    # Exclure tokens qui ressemblent à des codes agence / localité
    EXCLUDE = {'AG', 'RUE', 'BD', 'AV', 'TN', 'SA', 'STE', 'ETS',
               'CIE', 'SARL', 'SNC', 'GIE', 'TEL', 'FAX'}
    words = [w for w in words if w not in EXCLUDE]

    if len(words) < 2:
        return None
    return ' '.join(words[:2])


def _extraire_tireur(texte: str) -> Optional[str]:
    """
    Extrait le nom du titulaire (tireur) depuis le texte OCR.

    Stratégie 1 — avec label (cheques BIAT, Maghrebia...) :
      Recherche 'Titulaire du compte' ou 'صاحب الحساب' puis le nom qui suit.

    Stratégie 2 — sans label (cheques BTK, BT...) :
      Après le bloc RIB (20 chiffres), la ligne suivante = nom en MAJUSCULES.

    Stratégie 3 — fallback :
      Toute séquence de 2+ mots en MAJUSCULES dans la zone basse.
    """
    t = re.sub(r'\s+', ' ', texte.strip())

    # ── Stratégie 1 : après le label ──────────────────────────────────────
    label_patterns = [
        r'(?:titulaire\s*(?:de|du)\s*compte|صاحب\s*الحساب)\s*[:\-/]?\s*'
        r'([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-Za-zÀ-ÿ\s\.\-]{2,60})',
    ]
    for pat in label_patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip()
            # Couper aux stop words
            for stop in ('signature', 'non endossable', 'payez', 'date',
                         'montant', 'valable', 'agence', 'tel', 'fax'):
                idx = candidate.lower().find(stop)
                if idx > 0:
                    candidate = candidate[:idx].strip()
            result = _clean_tireur_name(candidate)
            if result:
                return result

    # ── Stratégie 2 : ligne après le RIB ─────────────────────────────────
    # Pattern : 20 chiffres (RIB) puis du texte sur la même ligne ou la suivante
    m = re.search(
        r'\d{20}[\s\S]{0,60}?([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,}(?:\s+[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,})+)',
        t)
    if m:
        result = _clean_tireur_name(m.group(1))
        if result:
            return result

    # ── Stratégie 3 : 2+ mots tout en MAJUSCULES ─────────────────────────
    # Cherche la séquence la plus longue de mots CAPS dans le texte
    sequences = re.findall(
        r'[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,}(?:\s+[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,}){1,4}', t)
    NOISE = {'TND', 'DT', 'RIB', 'CMC', 'QR', 'BCT', 'BTK', 'BIAT', 'BNA',
             'ATB', 'STB', 'UIB', 'QNB', 'BH', 'PAYEZ', 'CHEQUE', 'BANQUE',
             'AGENCE', 'DATE', 'MONTANT', 'SIGNATURE', 'VALABLE', 'NON',
             'ENDOSSABLE', 'ORDRE', 'PAYABLE', 'ARIANA', 'TUNIS', 'SFAX',
             'SOUSSE', 'NABEUL', 'BIZERTE', 'PECC'}
    for seq in sequences:
        words = [w for w in seq.split() if w not in NOISE and len(w) >= 2]
        if len(words) >= 2:
            result = _clean_tireur_name(' '.join(words))
            if result:
                return result

    return None


def _crop_positional_tireur(img: np.ndarray) -> list:
    """
    Retourne plusieurs crops couvrant les zones typiques du nom tireur
    pour n'importe quelle banque tunisienne.

    Zone ciblée : bas-gauche du chèque où apparaît le bloc RIB + nom.
    Plusieurs crops pour maximiser les chances de capturer le bon texte.
    """
    h, w = img.shape[:2]
    return [
        # Zone principale : bas-gauche (BIAT, Maghrebia, BNA...)
        img[int(h * 0.50):int(h * 0.82), int(w * 0.00):int(w * 0.62)],
        # Zone centrale basse (BTK, BT, Attijari...)
        img[int(h * 0.60):int(h * 0.84), int(w * 0.20):int(w * 0.80)],
        # Bande basse complète (fallback tous formats)
        img[int(h * 0.52):int(h * 0.88), :],
    ]


def _choisir_meilleure_passe(passes_resultats: list) -> tuple:
    """
    Choisit la meilleure passe OCR.

    LOGIQUE :
      La passe avec le plus de lignes n'est pas forcément la meilleure
      pour tous les champs. On favorise :
        - La passe qui extrait le montant (priorité absolue)
        - Sinon la passe avec le plus de texte utile

    Retourne (texte_general, texte_montant, nom_passe)
    """
    meilleur_txt    = ""
    meilleur_n      = 0
    meilleur_nom    = ""
    txt_pour_montant = None
    nom_montant      = ""

    for nom, txt, n in passes_resultats:
        if n > meilleur_n:
            meilleur_n   = n
            meilleur_txt = txt
            meilleur_nom = nom
        # Passe qui donne un montant valide → garder son texte
        if txt_pour_montant is None and _extraire_montant_strict(txt) is not None:
            txt_pour_montant = txt
            nom_montant      = nom

    # Utiliser le texte montant si trouvé, sinon texte général
    return meilleur_txt, txt_pour_montant, meilleur_nom, nom_montant


# ══════════════════════════════════════════════════════════════════════════
#  PREPROCESSING IMAGE
# ══════════════════════════════════════════════════════════════════════════

def _apply_exif_rotation(image_bytes: bytes) -> bytes:
    """Correction rotation EXIF avant cv2.imdecode (même raison que phase1)."""
    try:
        from PIL import Image, ImageOps
        import io
        pil_img = Image.open(io.BytesIO(image_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        buf = io.BytesIO()
        pil_img.save(buf, format="JPEG", quality=93)
        return buf.getvalue()
    except Exception:
        return image_bytes


def _normaliser(img: np.ndarray) -> np.ndarray:
    lum = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())
    if lum < 80:
        img = np.clip(img.astype(np.float32) * (150 / max(lum, 1)),
                      0, 255).astype(np.uint8)
    if lum < 160:
        lab   = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l,a,b = cv2.split(lab)
        l     = cv2.createCLAHE(2.5, (8, 8)).apply(l)
        img   = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
    return img


def _crop_zone(img: np.ndarray, box, pad: int = 15) -> np.ndarray:
    h, w = img.shape[:2]
    return img[max(0, int(box[1])-pad):min(h, int(box[3])+pad),
    max(0, int(box[0])-pad):min(w, int(box[2])+pad)]


# ══════════════════════════════════════════════════════════════════════════
#  CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════

class OCRYolo:
    """
    Moteur OCR robuste pour n'importe quel cheque tunisien.

    Philosophie :
      QR = source de verite (toujours disponible)
      OCR = detecteur de falsification (peut echouer sans bloquer)

    Utilisation dans phase2_compliance.py :
      self.ocr_yolo = OCRYolo()
      result = self.ocr_yolo.extraire(image_bytes)
    """

    def __init__(self, yolo_path: Optional[str] = None):
        self.yolo         = None
        self.yolo_phase3  = None  # Fallback — YOLO Phase 3 (plus complet)
        self._paddle      = None

        # Modèle YOLO principal Phase 2 (QR, num, RIB, date, montant_plafond)
        path = yolo_path or os.getenv("YOLO_PHASE2_PATH")
        if not path or not Path(path).exists():
            for candidat in YOLO_DEFAULT_PATHS:
                if Path(candidat).exists():
                    path = candidat
                    break

        if path and Path(path).exists():
            try:
                from ultralytics import YOLO
                self.yolo = YOLO(path)
                logger.info("yolo_phase2_pret", chemin=path)
            except Exception as e:
                logger.warning("yolo_phase2_erreur", error=str(e))
        else:
            logger.info("yolo_phase2_absent",
                        info="Mode OCR image complete actif")

        # ─── FALLBACK : YOLO Phase 3 (best_v24.pt — 14 classes) ──────────
        # Si YOLO Phase 2 ne détecte pas tous les champs, on utilise
        # YOLO Phase 3 qui a plus de classes entraînées.
        path3 = os.getenv("YOLO_PHASE3_PATH",
                          "saved_models/yolo_ocr/best_v24.pt")
        if Path(path3).exists():
            try:
                from ultralytics import YOLO
                self.yolo_phase3 = YOLO(path3)
                logger.info("yolo_phase3_fallback_pret", chemin=path3)
            except Exception as e:
                logger.warning("yolo_phase3_fallback_erreur", error=str(e))

    def _get_paddle(self):
        if self._paddle is None:
            try:
                from paddleocr import PaddleOCR
                self._paddle = PaddleOCR(use_angle_cls=True, lang="fr")
            except Exception as e:
                logger.warning("paddle_init_erreur", error=str(e))
        return self._paddle

    def _ocr_crop(self, crop: np.ndarray) -> str:
        """PaddleOCR sur un crop avec zoom si nécessaire."""
        ocr = self._get_paddle()
        if ocr is None or crop is None or crop.size == 0:
            return ""
        try:
            h, w = crop.shape[:2]
            if w < 200 or h < 25:
                scale = max(200/max(w,1), 25/max(h,1), 2.0)
                crop  = cv2.resize(crop,
                                   (int(w*scale), int(h*scale)),
                                   interpolation=cv2.INTER_CUBIC)
            r = self._get_paddle().ocr(_normaliser(crop), cls=True)
            if r and r[0]:
                return " ".join(str(l[1][0]) for l in r[0] if l)
        except Exception as e:
            logger.debug("ocr_crop_erreur", error=str(e))
        return ""

    # ══════════════════════════════════════════════════════════════════════
    #  MODE 1 — AVEC YOLO (precise, fiable)
    # ══════════════════════════════════════════════════════════════════════

    def _extraire_avec_yolo(self, img: np.ndarray) -> dict:
        """
        YOLO detecte les zones → OCR sur chaque crop.

        Avantage :
          Le crop de montant_plafond contient SEULEMENT la ligne du plafond.
          Pas de risque de confondre avec le numero de cheque.
          Regex simple et fiable.
        """
        result = {
            "numero_cheque": None, "rib":     None,
            "date":          None, "montant": None,
            "tireur":        None,
            "source_ocr":    "yolo+paddleocr",
            "ocr_disponible": False,
        }

        try:
            yolo_res = self.yolo(img, conf=0.10, verbose=False)[0]
        except Exception as e:
            logger.warning("yolo_inference_erreur", error=str(e))
            return self._extraire_sans_yolo(img)

        debug = Path("debug_crops")
        debug.mkdir(exist_ok=True)

        for box in yolo_res.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            nom    = YOLO_CLASSES.get(cls_id, "inconnu")
            crop   = _crop_zone(img, box.xyxy[0].tolist())
            if crop.size == 0: continue

            cv2.imwrite(str(debug / "{}.jpg".format(nom)), crop)
            texte = self._ocr_crop(crop)
            logger.debug("yolo_zone", nom=nom, conf=round(conf,2),
                         texte=texte[:50])

            # Extraction sur crop ciblé — pas de confusion possible
            if nom == "numero_cheque" and not result["numero_cheque"]:
                result["numero_cheque"] = _extraire_numero_cheque(texte)

            elif nom == "date" and not result["date"]:
                result["date"] = _extraire_date(texte)

            elif nom == "montant_plafond" and not result["montant"]:
                result["montant"] = _extraire_montant_strict(texte)

            elif nom == "rib_cmc7" and not result["rib"]:
                result["rib"] = _extraire_rib(texte)

        # Tireur : pas de classe YOLO dédiée → crops positionnels (liste)
        if not result["tireur"]:
            try:
                for crop_t in _crop_positional_tireur(img):
                    if crop_t is None or crop_t.size == 0:
                        continue
                    texte_t = self._ocr_crop(crop_t)
                    logger.debug("tireur_positional_ocr", texte=texte_t[:60])
                    result["tireur"] = _extraire_tireur(texte_t)
                    if result["tireur"]:
                        logger.info("tireur_phase2_extrait",
                                    tireur=result["tireur"][:40], methode="positionnel")
                        break
            except Exception as e:
                logger.debug("tireur_positional_erreur", error=str(e))

        result["ocr_disponible"] = any([
            result["numero_cheque"], result["date"],
            result["montant"], result["rib"]])

        n = sum(1 for v in [result["numero_cheque"], result["rib"],
                            result["date"], result["montant"]] if v)
        result["confiance"] = round(n / 4, 2)

        logger.info("ocr_yolo_done",
                    champs="{}/4".format(n),
                    num=result["numero_cheque"],
                    date=result["date"],
                    montant=result["montant"],
                    tireur=result["tireur"])
        return result

    # ══════════════════════════════════════════════════════════════════════
    #  FALLBACK — YOLO Phase 3 (best_v24.pt, 14 classes)
    # ══════════════════════════════════════════════════════════════════════

    def _extraire_avec_yolo_phase3(self, img: np.ndarray) -> dict:
        """
        Utilise YOLO Phase 3 (best_v24.pt) comme fallback quand Phase 2 échoue.
        Classes Phase 3 utilisées :
          2  = num_cheque
          7  = rib
          11 = date_expiration
          12 = montant_max (plafond)
        """
        result = {
            "numero_cheque": None, "rib":     None,
            "date":          None, "montant": None,
        }

        FIELDS_P3 = {
            2:  "numero_cheque",
            7:  "rib",
            11: "date",
            12: "montant",
        }

        try:
            y_res = self.yolo_phase3(img, conf=0.15, verbose=False)[0]
        except Exception as e:
            logger.warning("yolo_phase3_inference_erreur", error=str(e))
            return result

        for box in y_res.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in FIELDS_P3:
                continue
            champ = FIELDS_P3[cls_id]
            if result.get(champ):
                continue  # Déjà détecté

            crop = _crop_zone(img, box.xyxy[0].tolist())
            if crop.size == 0:
                continue

            texte = self._ocr_crop(crop)
            logger.debug("yolo_phase3_zone", nom=champ, texte=texte[:60])

            if champ == "numero_cheque":
                result[champ] = _extraire_numero_cheque(texte)
            elif champ == "rib":
                result[champ] = _extraire_rib(texte)
            elif champ == "date":
                result[champ] = _extraire_date(texte)
            elif champ == "montant":
                result[champ] = _extraire_montant_strict(texte)

        return result

    # ══════════════════════════════════════════════════════════════════════
    #  MODE 2 — SANS YOLO (image complète, 4 passes)
    # ══════════════════════════════════════════════════════════════════════

    def _extraire_sans_yolo(self, img: np.ndarray) -> dict:
        """
        OCR sur image complete avec selection intelligente des passes.

        LOGIQUE CORRECTE :
          - La passe avec LE PLUS DE LIGNES n'est pas forcément
            la meilleure pour extraire le montant.
          - On utilise une passe differente pour le montant si
            une autre passe le lit mieux.
          - Regex STRICTE sans fallback \b(\d{4,})\b dangereux.
        """
        result = {
            "numero_cheque": None, "rib":     None,
            "date":          None, "montant": None,
            "tireur":        None,
            "source_ocr":    None, "confiance": 0.0,
            "ocr_disponible": False,
        }

        ocr = self._get_paddle()
        if ocr is None:
            result["source_ocr"] = "paddle_indisponible"
            return result

        img_n = _normaliser(img.copy())
        h, w  = img_n.shape[:2]
        gray  = cv2.cvtColor(img_n, cv2.COLOR_BGR2GRAY)
        img_c = cv2.cvtColor(
            cv2.createCLAHE(2.0, (8, 8)).apply(gray), cv2.COLOR_GRAY2BGR)

        passes_def = [
            ("brute",         img_n),
            ("zoom_x2",       cv2.resize(img_n, (w*2, h*2),
                                         interpolation=cv2.INTER_CUBIC)),
            ("clahe",         img_c),
            ("zoom_x2+clahe", cv2.resize(img_c, (w*2, h*2),
                                         interpolation=cv2.INTER_CUBIC)),
        ]

        passes_resultats = []
        for nom, img_p in passes_def:
            try:
                r = ocr.ocr(img_p, cls=True)
                n = len(r[0]) if r and r[0] else 0
                if n > 0:
                    txt = " ".join(str(l[1][0]) for l in r[0] if l)
                    passes_resultats.append((nom, txt, n))
                    logger.debug("ocr_passe", nom=nom, n=n,
                                 montant=_extraire_montant_strict(txt))
            except Exception:
                pass

        if not passes_resultats:
            result["source_ocr"] = "paddleocr_echec_total"
            return result

        # Choisir intelligemment les passes
        txt_gen, txt_mont, nom_gen, nom_mont = \
            _choisir_meilleure_passe(passes_resultats)

        # Extraction depuis le texte general
        result["numero_cheque"] = _extraire_numero_cheque(txt_gen)
        result["date"]          = _extraire_date(txt_gen)
        result["rib"]           = _extraire_rib(re.sub(r'\s', '', txt_gen))
        result["tireur"] = _extraire_tireur(txt_gen)
        if result["tireur"]:
            logger.info("tireur_phase2_extrait",
                        tireur=result["tireur"][:40], methode="regex_texte_complet")
        else:
            try:
                for crop_t in _crop_positional_tireur(img_n):
                    if crop_t is None or crop_t.size == 0:
                        continue
                    texte_t = self._ocr_crop(crop_t)
                    result["tireur"] = _extraire_tireur(texte_t)
                    if result["tireur"]:
                        logger.info("tireur_phase2_extrait",
                                    tireur=result["tireur"][:40], methode="positionnel_fallback")
                        break
            except Exception as e:
                logger.debug("tireur_positional_fallback_erreur", error=str(e))

        # Montant : utiliser la MEILLEURE passe pour le montant
        # (peut etre differente de la passe generale)
        if txt_mont:
            result["montant"]  = _extraire_montant_strict(txt_mont)
            result["source_ocr"] = "paddleocr_{}_mont:{}".format(
                nom_gen, nom_mont)
        else:
            result["source_ocr"] = "paddleocr_{}".format(nom_gen)

        result["ocr_disponible"] = any([
            result["numero_cheque"], result["date"],
            result["montant"], result["rib"]])

        n = sum(1 for v in [result["numero_cheque"], result["rib"],
                            result["date"], result["montant"]] if v)
        result["confiance"] = round(n / 4 * 0.80, 2)

        logger.info("ocr_fallback_done",
                    champs="{}/4".format(n),
                    source=result["source_ocr"],
                    montant=result["montant"])
        return result

    # ══════════════════════════════════════════════════════════════════════
    #  POINT D'ENTREE — ENRICHISSEMENT PAR QR
    # ══════════════════════════════════════════════════════════════════════

    def extraire(self, image_bytes: bytes,
                 qr_data: Optional[dict] = None) -> dict:
        """
        Extrait les champs physiques du cheque.

        ARGUMENT qr_data : donnees du QR (si deja decodees en Phase 2)
          → Permet d'enrichir le resultat OCR avec les valeurs QR
          → Et de detecter les falsifications

        Retourne un dict avec :
          numero_cheque, rib, date, montant  → valeurs OCR physiques
          ocr_disponible                     → False si OCR a totalement echoue
          source_ocr                         → origine de l'extraction
          comparaison                        → si qr_data fourni
        """
        image_bytes = _apply_exif_rotation(image_bytes)
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return {
                "numero_cheque": None, "rib": None,
                "date": None, "montant": None,
                "ocr_disponible": False, "source_ocr": "image_illisible",
            }

        img = _normaliser(img)

        # Extraire via YOLO Phase 2 (en priorité)
        if self.yolo:
            result = self._extraire_avec_yolo(img)
        else:
            result = self._extraire_sans_yolo(img)

        # ─── FALLBACK YOLO Phase 3 ─────────────────────────────────────
        # Si YOLO Phase 2 n'a pas détecté tous les champs, on complète
        # avec YOLO Phase 3 (modèle plus complet, 14 classes).
        champs_manquants = sum(1 for k in ["numero_cheque", "rib",
                                           "date", "montant"]
                               if not result.get(k))
        if champs_manquants >= 2 and self.yolo_phase3:
            logger.info("fallback_yolo_phase3_active",
                        champs_manquants=champs_manquants)
            try:
                res3 = self._extraire_avec_yolo_phase3(img)
                # Fusionner : garder Phase 2 si présent, sinon Phase 3
                for k in ["numero_cheque", "rib", "date", "montant"]:
                    if not result.get(k) and res3.get(k):
                        result[k] = res3[k]
                        logger.info("yolo_phase3_complete",
                                    champ=k, valeur=str(res3[k])[:30])
                # Marquer la source mixte
                if any(res3.get(k) for k in ["numero_cheque","rib","date","montant"]):
                    result["source_ocr"] = "yolo_phase2+phase3"
                # Recompter
                n = sum(1 for v in [result.get("numero_cheque"),
                                    result.get("rib"),
                                    result.get("date"),
                                    result.get("montant")] if v)
                result["confiance"] = round(n / 4, 2)
                result["ocr_disponible"] = n > 0
            except Exception as e:
                logger.warning("yolo_phase3_fallback_erreur",
                               error=str(e)[:60])

        # ─── CMC7 — compléter rib + agence si manquants ───────────────────
        if _CMC7_OK:
            try:
                chiffres = lire_ligne_cmc7(img)
                if chiffres:
                    parsed = parser_cmc7(chiffres)
                    # Compléter le RIB si OCR n'en a pas trouvé
                    if not result.get("rib") and parsed.get("rib"):
                        result["rib"] = parsed["rib"]
                        logger.info("rib_depuis_cmc7", rib=parsed["rib"])
                    # Numéro chèque depuis CMC7 si manquant
                    if not result.get("numero_cheque") and parsed.get("num_cheque"):
                        result["numero_cheque"] = parsed["num_cheque"]
                    # Agence bancaire (toujours utile)
                    if parsed.get("code_banque") and parsed.get("code_agence"):
                        result["agence"] = lookup_agence(
                            parsed["code_banque"], parsed["code_agence"])
                        result["code_banque"] = parsed["code_banque"]
                    logger.info("cmc7_enrichissement",
                                agence=result.get("agence"),
                                rib_ok=bool(result.get("rib")))
            except Exception as e:
                logger.debug("cmc7_enrichissement_erreur", error=str(e))

        # Enrichissement : si QR disponible, signaler si OCR doit
        # etre utilise comme detecteur de falsification uniquement
        if qr_data and qr_data.get("is_pecc"):
            result["note"] = (
                "OCR utilise pour detection falsification. "
                "QR pecc.tn est la source de verite."
            )

        return result

    @property
    def yolo_disponible(self) -> bool:
        return self.yolo is not None