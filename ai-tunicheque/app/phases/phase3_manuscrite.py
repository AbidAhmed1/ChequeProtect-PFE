"""
app/phases/phase3_manuscrite.py
================================
Phase 3 — Extraction zones manuscrites + comparaison montants.

CLASSES YOLO PHASE 3 (best_phase3.pt) :
    0 : beneficiaire
    1 : montant_chiffres
    2 : montant_lettres

STRUCTURE RÉELLE DU CHÈQUE TUNISIEN :
    ┌────────────────────────────────────────────────────┐
    │  Payez contre ce chèque non endossable sauf...     │
    │  ادفعوا مقابل هذا الصك...                          │
    │  [zone montant_chiffres encadrée par MakeSense]    │
    │  → "BPD # 5000 #" ou "5000" ou vide               │
    │                                                    │
    │  A l'ordre de .....................................│
    │  لامر                                              │
    │  [zone beneficiaire encadrée par MakeSense]        │
    │  → "M. Ahmed Ben Ali" ou vide                      │
    │                                                    │
    │  La somme de ......................................│
    │  [zone montant_lettres encadrée par MakeSense]     │
    │  → "cinq mille dinars" ou vide                     │
    └────────────────────────────────────────────────────┘

PIPELINE :
    YOLO → crop → Prétraitement → OCR → Nettoyage → Conversion → Comparaison

USAGE :
    from app.phases.phase3_manuscrite import Phase3Manuscrite
    p3     = Phase3Manuscrite()
    result = p3.extraire(image_bytes, qr_montant=5000.0)
    print(result["comparaison"]["statut"])  # CONFORME / FALSIFICATION
"""

import os, re, cv2, pickle
import numpy as np
from pathlib import Path
from typing import Optional, List, Tuple

try:
    from app.phases.cheque_cleaner import (
        extraire_champs_par_ancrage,
        extraire_date_du_texte,
    )
    _CLEANER_OK = True
except ImportError:
    _CLEANER_OK = False

os.environ["FLAGS_use_mkldnn"]       = "0"
os.environ["GLOG_minloglevel"]       = "3"
os.environ["FLAGS_call_stack_level"] = "0"

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    class _Logger:
        def __init__(self):
            self._log = logging.getLogger("phase3")
        def _fmt(self, msg, kw):
            extras = " | ".join("{}={}".format(k,v) for k,v in kw.items())
            return "{} | {}".format(msg, extras) if extras else msg
        def info(self, msg, **kw):    self._log.info(self._fmt(msg, kw))
        def warning(self, msg, **kw): self._log.warning(self._fmt(msg, kw))
        def error(self, msg, **kw):   self._log.error(self._fmt(msg, kw))
        def debug(self, msg, **kw):   self._log.debug(self._fmt(msg, kw))
    logger = _Logger()

# ── Chemins ──────────────────────────────────────────────────────────────
YOLO_PHASE3_PATH = "saved_models/yolo_phase3/weights/best_phase3.pt"
SVM_PATH         = "saved_models/svm_montant_lettres.pkl"

# ── Classes YOLO Phase 3 — ORDRE FIXE ────────────────────────────────────
CLASSES_P3 = {
    0: "beneficiaire",
    1: "montant_chiffres",
    2: "montant_lettres",
}


# ══════════════════════════════════════════════════════════════════════════
#  DICTIONNAIRE BANCAIRE TUNISIEN FR + AR
# ══════════════════════════════════════════════════════════════════════════

VOCABULAIRE_BANCAIRE = [
    # Français
    "un","une","deux","trois","quatre","cinq","six","sept","huit","neuf",
    "dix","onze","douze","treize","quatorze","quinze","seize",
    "dix-sept","dix-huit","dix-neuf",
    "vingt","trente","quarante","cinquante",
    "soixante","soixante-dix","quatre-vingt","quatre-vingt-dix",
    "cent","cents","mille","dinar","dinars","millime","millimes",
    # Arabe
    "واحد","اثنان","اثنين","ثلاثة","أربعة","خمسة","ستة","سبعة","ثمانية","تسعة",
    "عشرة","عشرون","ثلاثون","أربعون","خمسون","ستون","سبعون","ثمانون","تسعون",
    "مائة","مئة","ألف","دينار","دنانير","مليم",
]

MOT_VERS_VALEUR = {
    "zéro":0,"zero":0,
    "un":1,"une":1,"واحد":1,
    "deux":2,"اثنان":2,"اثنين":2,
    "trois":3,"ثلاثة":3,
    "quatre":4,"أربعة":4,
    "cinq":5,"خمسة":5,
    "six":6,"ستة":6,
    "sept":7,"سبعة":7,
    "huit":8,"ثمانية":8,
    "neuf":9,"تسعة":9,
    "dix":10,"عشرة":10,
    "onze":11,"douze":12,"treize":13,"quatorze":14,"quinze":15,"seize":16,
    "dix-sept":17,"dix-huit":18,"dix-neuf":19,
    "vingt":20,"عشرون":20,
    "trente":30,"ثلاثون":30,
    "quarante":40,"أربعون":40,
    "cinquante":50,"خمسون":50,
    "soixante":60,"ستون":60,
    "soixante-dix":70,"سبعون":70,
    "quatre-vingt":80,"ثمانون":80,
    "quatre-vingt-dix":90,"تسعون":90,
    "cent":100,"cents":100,"مائة":100,"مئة":100,
    "mille":1000,"ألف":1000,"ألفان":2000,
}

MOTS_IGNORES = {
    "et","dinars","dinar","dt","tnd","millimes","millime",
    "la","le","les","de","du","des","somme","montant","la somme",
    "payez","contre","cheque","chèque","endossable","sauf","profit",
    "banque","organisme",
    "دينار","دنانير","مليم","مليمات","ادفعوا","مقابل","هذا","الصك",
}


# ══════════════════════════════════════════════════════════════════════════
#  FONCTIONS D'EXTRACTION SPÉCIFIQUES AU CHÈQUE TUNISIEN
# ══════════════════════════════════════════════════════════════════════════

def _extraire_montant_chiffres(texte: str) -> Optional[float]:
    """
    Extrait le montant numérique depuis la zone chèque.

    Formats réels observés :
      "BPD # 5000 #"        → 5000.0  (BPD imprimé, # et chiffre manuscrits)
      "BPD # 5 000 #"       → 5000.0  (espace = séparateur milliers)
      "BPD # 5.000 #"       → 5000.0  (point = séparateur milliers)
      "5000"                → 5000.0  (sans BPD)
      "5 000"               → 5000.0
      "Payez ... 5000 ..."  → 5000.0  (texte imprimé inclus dans le crop)
      ""  ou  " "           → None    (zone vide = chèque non rempli)
    """
    if not texte or not texte.strip():
        return None

    t = texte.upper()

    # Supprimer le texte imprimé parasite
    textes_imprimes = [
        r'PAYEZ CONTRE CE CH[EÈ]QUE.*',
        r'ادفعوا مقابل.*',
        r'NON ENDOSSABLE.*',
        r'BPD\.?',
    ]
    for pat in textes_imprimes:
        t = re.sub(pat, '', t, flags=re.IGNORECASE)

    # Supprimer les #
    t = re.sub(r'#', '', t)

    # Garder uniquement chiffres, espace, virgule, point
    t = re.sub(r'[^\d\s,.]', ' ', t).strip()

    if not t:
        return None

    # Normaliser les séparateurs de milliers
    t = re.sub(r'(\d)\s+(\d)',       r'\1\2', t)  # "5 000"  → "5000"
    t = re.sub(r'(\d)\.(\d{3})\b',  r'\1\2', t)  # "5.000"  → "5000"
    t = re.sub(r'(\d),(\d{3})\b',   r'\1\2', t)  # "5,000"  → "5000"

    # Extraire le premier nombre valide
    m = re.search(r'\b(\d+(?:[.,]\d{1,2})?)\b', t)
    if m:
        try:
            v = float(m.group(1).replace(',', '.'))
            if 1 <= v <= 30_000:
                return v
        except ValueError:
            pass
    return None


def _nettoyer_beneficiaire(texte: str) -> Optional[str]:
    """
    Supprime les préfixes imprimés de la zone bénéficiaire.

    Formats réels :
      "A l'ordre de M. Ahmed Ben Ali"  → "M. Ahmed Ben Ali"
      "A l'ordre de Société XYZ"       → "Société XYZ"
      "لامر Ahmed Ben Ali"              → "Ahmed Ben Ali"
      "M. Ahmed Ben Ali"               → "M. Ahmed Ben Ali"  (inchangé)
    """
    if not texte or not texte.strip():
        return None

    t = texte.strip()

    prefixes = [
        r"^[Aa]\s*l['']?\s*ordre\s*de\s*",
        r"^[Àà]\s*l[ée]?\s*ordre\s*de\s*",
        r"^À\s*l'ordre\s*de\s*",
        r'^لامر\s*',
        r'^ل\s*أمر\s*',
        r'^order\s*of\s*',
    ]
    for pat in prefixes:
        t = re.sub(pat, '', t, flags=re.IGNORECASE).strip()

    return t if t else None


# ══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 1 — PRÉTRAITEMENT MANUSCRIT
# ══════════════════════════════════════════════════════════════════════════

def binariser_sauvola(gray: np.ndarray) -> np.ndarray:
    """
    Binarisation locale Sauvola.
    Adapte le seuil à chaque région → gère les fonds de sécurité des chèques.
    Fallback automatique vers seuillage adaptatif Gaussien (OpenCV) si
    scikit-image non installé.
    """
    try:
        from skimage.filters import threshold_sauvola
        thresh = threshold_sauvola(gray, window_size=25)
        return ((gray < thresh) * 255).astype(np.uint8)
    except ImportError:
        return cv2.adaptiveThreshold(
            gray, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 8)


def corriger_skew(img_bin: np.ndarray) -> Tuple[np.ndarray, float]:
    """
    Correction d'inclinaison (Skew) par histogramme de projection.

    Principe :
      - Faire pivoter l'image de -10° à +10° par pas de 0.5°
      - Pour chaque angle, calculer la variance de l'histogramme horizontal
        (nombre de pixels noirs par ligne)
      - L'angle correct maximise la variance : les lignes de texte
        sont bien alignées → les projections forment des pics nets
    """
    h, w = img_bin.shape[:2]
    meilleur_score = -1.0
    meilleur_angle = 0.0

    for angle in np.arange(-10, 10.5, 0.5):
        M     = cv2.getRotationMatrix2D((w/2, h/2), angle, 1.0)
        rotee = cv2.warpAffine(img_bin, M, (w, h),
                               flags=cv2.INTER_NEAREST, borderValue=0)
        hist  = np.sum(rotee > 0, axis=1).astype(np.float64)
        score = float(np.var(hist))
        if score > meilleur_score:
            meilleur_score = score
            meilleur_angle = angle

    if abs(meilleur_angle) < 0.5:
        return img_bin, 0.0

    M = cv2.getRotationMatrix2D((w/2, h/2), meilleur_angle, 1.0)
    corrigee = cv2.warpAffine(img_bin, M, (w, h),
                              flags=cv2.INTER_CUBIC,
                              borderMode=cv2.BORDER_REPLICATE)
    return corrigee, meilleur_angle


def pretraiter_crop_manuscrit(crop: np.ndarray) -> Optional[np.ndarray]:
    """
    Pipeline prétraitement complet pour écriture manuscrite :
      1. Agrandir (min 500×50 pixels) pour améliorer la lecture OCR
      2. Binarisation Sauvola (locale, gère les fonds de sécurité)
      3. Correction Skew (redresser la ligne d'écriture)
      4. Dilatation légère (raccorder les traits cursifs français)
    """
    if crop is None or crop.size == 0:
        return None

    # 1. Agrandir si trop petit
    h, w  = crop.shape[:2]
    scale = max(500/max(w, 1), 50/max(h, 1), 1.0)
    if scale > 1.0:
        crop = cv2.resize(crop, (int(w*scale), int(h*scale)),
                          interpolation=cv2.INTER_CUBIC)

    # 2. Niveaux de gris + Sauvola
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) \
        if len(crop.shape) == 3 else crop.copy()
    bw   = binariser_sauvola(gray)

    # 3. Correction Skew
    bw, angle = corriger_skew(bw)

    # 4. Dilatation légère (raccorder traits cursifs)
    kernel = np.ones((2, 1), np.uint8)
    bw     = cv2.dilate(bw, kernel, iterations=1)

    return cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR)


# ══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 2 — SEGMENTATION MOT PAR MOT
# ══════════════════════════════════════════════════════════════════════════

def segmenter_mots(img_bin: np.ndarray) -> List[np.ndarray]:
    """
    Segmentation mot par mot via composantes connexes.

    Algorithme :
      1. Trouver toutes les composantes connexes (blocs d'encre)
      2. Trier les blocs de gauche à droite
      3. Calculer la distance horizontale entre blocs consécutifs
      4. Seuil automatique = médiane des distances × 1.5
         - petite distance → même mot
         - grande distance → nouveau mot
      5. Regrouper les blocs proches → extraire le crop de chaque mot

    Retourne : liste de crops numpy, un par mot.
    """
    if img_bin is None or img_bin.size == 0:
        return []

    gray = cv2.cvtColor(img_bin, cv2.COLOR_BGR2GRAY) \
        if len(img_bin.shape) == 3 else img_bin.copy()
    _, bw = cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)

    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        bw, connectivity=8)

    if n_labels <= 1:
        return [img_bin]

    boxes = []
    for i in range(1, n_labels):
        area = stats[i, cv2.CC_STAT_AREA]
        if area < 30: continue
        x = stats[i, cv2.CC_STAT_LEFT]
        y = stats[i, cv2.CC_STAT_TOP]
        w = stats[i, cv2.CC_STAT_WIDTH]
        h = stats[i, cv2.CC_STAT_HEIGHT]
        boxes.append((x, y, w, h))

    if not boxes:
        return [img_bin]

    boxes.sort(key=lambda b: b[0])

    distances = []
    for i in range(1, len(boxes)):
        bord_d = boxes[i-1][0] + boxes[i-1][2]
        bord_g = boxes[i][0]
        distances.append(max(0, bord_g - bord_d))

    if not distances:
        return [img_bin]

    seuil = max(float(np.median(distances)) * 1.5, 5.0)

    groupes = [[boxes[0]]]
    for i, dist in enumerate(distances):
        if dist > seuil:
            groupes.append([boxes[i+1]])
        else:
            groupes[-1].append(boxes[i+1])

    H, W  = img_bin.shape[:2]
    crops = []
    for groupe in groupes:
        x1 = max(0, min(b[0]       for b in groupe) - 4)
        y1 = max(0, min(b[1]       for b in groupe) - 4)
        x2 = min(W, max(b[0]+b[2]  for b in groupe) + 4)
        y2 = min(H, max(b[1]+b[3]  for b in groupe) + 4)
        c  = img_bin[y1:y2, x1:x2]
        if c.size > 100:
            crops.append(c)

    return crops if crops else [img_bin]


# ══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 3 — FEATURES + SVM
# ══════════════════════════════════════════════════════════════════════════

def extraire_matrice_distribution(img: np.ndarray,
                                  n_blocs: int = 13) -> np.ndarray:
    """
    Matrice de distribution de pixels noirs (Document 2).
    Divise l'image 130×130 en 13×13 blocs → 169 features.
    Chaque feature = ratio de pixels noirs dans le bloc.
    Language-agnostique : fonctionne pour le français ET l'arabe.
    """
    taille = n_blocs * 10
    if len(img.shape) == 3:
        img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    img_r  = cv2.resize(img, (taille, taille), interpolation=cv2.INTER_AREA)
    _, bw  = cv2.threshold(img_r, 127, 255, cv2.THRESH_BINARY_INV)
    bloc   = taille // n_blocs
    feats  = []
    for i in range(n_blocs):
        for j in range(n_blocs):
            zone  = bw[i*bloc:(i+1)*bloc, j*bloc:(j+1)*bloc]
            ratio = float(np.sum(zone > 0)) / max(zone.size, 1)
            feats.append(ratio)
    return np.array(feats, dtype=np.float32)


class SVMManuscrit:
    """
    SVM multiclasse One-vs-One (sklearn.svm.SVC, ovo).
    Reconnaît les mots bancaires manuscrits.
    Chargé automatiquement si saved_models/svm_montant_lettres.pkl existe.
    """

    def __init__(self):
        self.model    = None
        self.classes_ = []
        self._charger()

    def _charger(self):
        if Path(SVM_PATH).exists():
            try:
                with open(SVM_PATH, "rb") as f:
                    data          = pickle.load(f)
                self.model    = data["model"]
                self.classes_ = data["classes"]
                logger.info("svm_charge", n_classes=len(self.classes_))
            except Exception as e:
                logger.warning("svm_erreur", error=str(e))

    @property
    def disponible(self) -> bool:
        return self.model is not None

    def predire(self, img: np.ndarray) -> Tuple[str, float]:
        """Retourne (mot_prédit, confiance)."""
        if not self.disponible:
            return "", 0.0
        try:
            ft    = extraire_matrice_distribution(img).reshape(1, -1)
            proba = self.model.predict_proba(ft)[0]
            idx   = int(np.argmax(proba))
            return self.classes_[idx], float(proba[idx])
        except Exception as e:
            logger.debug("svm_pred_erreur", error=str(e))
            return "", 0.0

    @staticmethod
    def entrainer(dossier: str = "dataset_svm"):
        """
        Entraîne le SVM.
        Structure attendue :
          dataset_svm/
            cinq/    ← 20-30 images de "cinq" manuscrit
            mille/   ← 20-30 images de "mille" manuscrit
            cent/    ← etc.
        """
        from sklearn.svm import SVC
        from sklearn.preprocessing import StandardScaler
        from sklearn.pipeline import Pipeline
        from sklearn.model_selection import cross_val_score

        X, y    = [], []
        d_path  = Path(dossier)
        classes = []

        if not d_path.exists():
            print(f"Dossier {dossier} introuvable")
            return None

        for cls_dir in sorted(d_path.iterdir()):
            if not cls_dir.is_dir(): continue
            imgs = list(cls_dir.glob("*.jpg")) + list(cls_dir.glob("*.png"))
            if not imgs:
                continue
            classes.append(cls_dir.name)
            print(f"  {cls_dir.name} : {len(imgs)} images")
            for img_p in imgs:
                img = cv2.imread(str(img_p), cv2.IMREAD_GRAYSCALE)
                if img is None: continue
                bw  = binariser_sauvola(img)
                X.append(extraire_matrice_distribution(bw))
                y.append(cls_dir.name)

        if len(X) < 10:
            print(f"Pas assez d'images ({len(X)})")
            return None

        X_arr = np.array(X)
        y_arr = np.array(y)
        print(f"\nDataset : {len(X_arr)} exemples, {len(set(y_arr))} classes")

        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("svm", SVC(
                kernel="rbf", C=10, gamma="scale",
                decision_function_shape="ovo",  # One-vs-One (Document 2)
                probability=True, random_state=42,
            ))
        ])

        scores = cross_val_score(pipeline, X_arr, y_arr, cv=5)
        print(f"Validation croisée : {scores.mean()*100:.1f}% ± {scores.std()*100:.1f}%")

        pipeline.fit(X_arr, y_arr)
        Path(SVM_PATH).parent.mkdir(parents=True, exist_ok=True)
        with open(SVM_PATH, "wb") as f:
            pickle.dump({"model": pipeline, "classes": classes}, f)
        print(f"SVM sauvegardé : {SVM_PATH}")
        return pipeline


# ══════════════════════════════════════════════════════════════════════════
#  ÉTAPE 4 — CORRECTION LEXICALE (Levenshtein)
# ══════════════════════════════════════════════════════════════════════════

def corriger_mot(mot: str, seuil: int = 72) -> Tuple[str, int]:
    """
    Corrige un mot OCR par distance de Levenshtein vers le vocabulaire bancaire.
    Exemples : "veingt"→"vingt"(88%), "cinqs"→"cinq"(91%), "mi1le"→"mille"(91%)
    Utilise TheFuzz si installé, sinon difflib (Python standard).
    """
    if not mot or len(mot) <= 1:
        return mot, 100
    mot_l = mot.lower().strip()
    if mot_l in MOT_VERS_VALEUR or mot_l in MOTS_IGNORES:
        return mot_l, 100
    try:
        from thefuzz import process
        res = process.extractOne(mot_l, VOCABULAIRE_BANCAIRE,
                                 score_cutoff=seuil)
        if res:
            return res[0], res[1]
    except ImportError:
        from difflib import get_close_matches
        m = get_close_matches(mot_l, VOCABULAIRE_BANCAIRE, n=1, cutoff=0.65)
        if m:
            return m[0], 75
    return mot_l, 0


def corriger_texte(texte: str) -> str:
    """Corrige tous les mots d'un texte OCR par Levenshtein."""
    if not texte:
        return ""
    mots     = texte.strip().split()
    corriges = []
    for mot in mots:
        mot_c, score = corriger_mot(mot)
        corriges.append(mot_c if score >= 72 else mot.lower())
    return " ".join(corriges)


def convertir_lettres_vers_nombre(texte: str) -> Optional[float]:
    """
    Convertit un montant en lettres en nombre.

    Algorithme :
      total   = 0  (résultat final)
      courant = 0  (groupe en cours : ex "deux cent")
      Pour chaque mot valide :
        = 1000 → total += max(courant,1)×1000 ; courant = 0
        = 100  → courant = max(courant,1)×100
        sinon  → courant += valeur
      Fin → total += courant

    Exemples :
      "cinq mille dinars"          → 5000.0
      "deux cent cinquante dinars" → 250.0
      "mille cinq cents"           → 1500.0
      "vingt"                      → 20.0
    """
    if not texte:
        return None

    # Cas : l'OCR a directement retourné un chiffre
    m = re.search(r'\b(\d+(?:[.,]\d+)?)\b', texte)
    if m:
        try:
            v = float(m.group(1).replace(',', '.'))
            if 1 <= v <= 30_000:
                return v
        except ValueError:
            pass

    texte_c = corriger_texte(texte)
    mots    = [m for m in re.split(r'[\s\-]+', texte_c)
               if m and m not in MOTS_IGNORES]

    total = courant = 0.0
    for mot in mots:
        val = MOT_VERS_VALEUR.get(mot)
        if val is None:
            mot2, _ = corriger_mot(mot)
            val      = MOT_VERS_VALEUR.get(mot2)
        if val is None:
            continue
        if val == 1000:
            courant  = max(courant, 1.0) * 1000
            total   += courant
            courant  = 0.0
        elif val == 100:
            courant  = max(courant, 1.0) * 100
        else:
            courant += val

    total += courant
    return round(total, 3) if total > 0 else None


# ══════════════════════════════════════════════════════════════════════════
#  COMPARAISON MONTANTS
# ══════════════════════════════════════════════════════════════════════════

def comparer_montants(montant_chiffres: Optional[float],
                      texte_lettres: str,
                      tolerance_pct: float = 0.01) -> dict:
    """
    Compare le montant en chiffres avec le montant en lettres converti.
    Tolérance = 1% (centimes arrondis).

    Retourne :
      statut :
        CONFORME        → chiffres ≈ lettres ✓
        FALSIFICATION   → chiffres ≠ lettres → alerter
        OCR_INSUFFISANT → lettres illisibles → agent vérifie manuellement
    """
    texte_corrige = corriger_texte(texte_lettres)
    montant_ltr   = convertir_lettres_vers_nombre(texte_corrige)

    base = {
        "texte_ocr_brut":   texte_lettres,
        "texte_corrige":    texte_corrige,
        "montant_chiffres": montant_chiffres,
        "montant_lettres":  montant_ltr,
    }

    if montant_chiffres is None:
        return {**base,
                "statut": "OCR_INSUFFISANT",
                "detail": "Montant en chiffres non extrait — zone vide ou illisible"}

    if montant_ltr is None:
        return {**base,
                "statut": "OCR_INSUFFISANT",
                "detail": f"Montant en lettres non convertible : '{texte_corrige}'"}

    diff     = abs(montant_chiffres - montant_ltr)
    seuil    = max(1.0, montant_chiffres * tolerance_pct)
    conforme = diff <= seuil

    return {**base,
            "statut":     "CONFORME" if conforme else "FALSIFICATION",
            "detail":     f"Différence : {diff:.2f} DT (seuil {seuil:.1f} DT)",
            "difference": diff,
            "conforme":   conforme}


# ══════════════════════════════════════════════════════════════════════════
#  PADDLEOCR — Singleton
# ══════════════════════════════════════════════════════════════════════════

_paddle_p3 = None

def _get_paddle():
    global _paddle_p3
    if _paddle_p3 is None:
        try:
            from paddleocr import PaddleOCR
            _paddle_p3 = PaddleOCR(
                use_angle_cls=True,
                lang         ="fr",
                enable_mkldnn=False,
                use_gpu      =False,
                show_log     =False,
            )
        except Exception as e:
            logger.warning("paddle_p3_init_erreur", error=str(e))
    return _paddle_p3


def _ocr_crop(crop: np.ndarray) -> str:
    """
    PaddleOCR sur un crop avec 2 passes :
      Passe 1 : crop prétraité (Sauvola + redressement)
      Passe 2 : crop original agrandi ×2
    Retourne le texte le plus riche.
    """
    ocr = _get_paddle()
    if ocr is None or crop is None or crop.size == 0:
        return ""

    resultats = []
    h, w      = crop.shape[:2]

    # Passe 1 : prétraitement Sauvola
    crop_prep = pretraiter_crop_manuscrit(crop.copy())
    if crop_prep is not None:
        try:
            r = ocr.ocr(crop_prep, cls=True)
            if r and r[0]:
                txt = " ".join(str(l[1][0]) for l in r[0] if l)
                if txt.strip():
                    resultats.append((len(txt.split()), txt))
        except Exception:
            pass

    # Passe 2 : zoom ×2 sur crop original
    try:
        crop2 = cv2.resize(crop, (w*2, h*2), interpolation=cv2.INTER_CUBIC)
        r     = ocr.ocr(crop2, cls=True)
        if r and r[0]:
            txt = " ".join(str(l[1][0]) for l in r[0] if l)
            if txt.strip():
                resultats.append((len(txt.split()), txt))
    except Exception:
        pass

    if not resultats:
        return ""
    resultats.sort(key=lambda x: x[0], reverse=True)
    return resultats[0][1]


# ══════════════════════════════════════════════════════════════════════════
#  CLASSE PRINCIPALE
# ══════════════════════════════════════════════════════════════════════════

class Phase3Manuscrite:
    """
    Orchestrateur Phase 3 — Zones manuscrites du chèque tunisien.

    Usage dans le pipeline :
        from app.phases.phase3_manuscrite import Phase3Manuscrite
        p3     = Phase3Manuscrite()
        result = p3.extraire(image_bytes, qr_montant=5000.0)
    """

    def __init__(self, yolo_path: str = YOLO_PHASE3_PATH):
        self._yolo = None
        self._svm  = SVMManuscrit()

        if Path(yolo_path).exists():
            try:
                from ultralytics import YOLO
                self._yolo = YOLO(yolo_path)
                logger.info("yolo_p3_charge", chemin=yolo_path)
            except Exception as e:
                logger.warning("yolo_p3_erreur", error=str(e))
        else:
            logger.warning("yolo_p3_absent", chemin=yolo_path,
                           info="Annoter dans MakeSense → Colab → best_phase3.pt")

        logger.info("phase3_init",
                    yolo=self._yolo is not None,
                    svm =self._svm.disponible)

    def _lire_montant_lettres(self, crop: np.ndarray) -> str:
        """
        Lecture spécialisée du crop montant_lettres.
        Stratégie :
          1. Si SVM disponible → segmenter mot par mot → SVM + Levenshtein
          2. Sinon → PaddleOCR (2 passes) + Levenshtein
        """
        if self._svm.disponible:
            bw = pretraiter_crop_manuscrit(crop.copy())
            if bw is None:
                return ""

            mots_crops = segmenter_mots(bw)
            mots_lus   = []
            debug      = Path("debug_crops")
            debug.mkdir(exist_ok=True)

            for i, mot_crop in enumerate(mots_crops):
                cv2.imwrite(str(debug / f"p3_mot_{i}.jpg"), mot_crop)
                mot, conf = self._svm.predire(mot_crop)
                if conf >= 0.60:
                    mot_c, _ = corriger_mot(mot)
                    if mot_c:
                        mots_lus.append(mot_c)

            return " ".join(mots_lus) if mots_lus else ""
        else:
            # Fallback PaddleOCR
            return _ocr_crop(crop)

    def _extraire_par_ancrage(self, img: np.ndarray,
                              qr_montant: Optional[float],
                              result: dict) -> dict:
        """
        Fallback sans YOLO : utilise cheque_cleaner.extraire_champs_par_ancrage()
        (ancrage par mots-clés + EasyOCR) pour extraire bénéficiaire, date, lieu.
        """
        try:
            champs = extraire_champs_par_ancrage(img)
        except Exception as e:
            logger.warning("ancrage_erreur", error=str(e))
            return result

        result["beneficiaire"]    = champs.get("beneficiaire")
        result["ancrage_lieu"]    = champs.get("lieu")
        result["ancrage_agence"]  = champs.get("agence")
        result["ancrage_tireur_rib"] = champs.get("tireur_rib")
        result["methode_fallback"]   = "ancrage"

        # Date issue de l'ancrage (peut servir à phase2 si transmis)
        if champs.get("date"):
            result["date_emission"] = champs["date"]

        # Comparaison des montants si disponible
        if result.get("montant_lettres") and qr_montant is not None:
            result["comparaison"] = comparer_montants(
                qr_montant, result["montant_lettres"])
            result["falsification"] = \
                result["comparaison"].get("statut") == "FALSIFICATION"
        else:
            result["comparaison"] = {
                "statut": "OCR_INSUFFISANT",
                "detail": "YOLO absent — ancrage actif, montant lettres non extrait",
            }

        logger.info("ancrage_done",
                    beneficiaire=result["beneficiaire"],
                    date=result.get("date_emission"),
                    lieu=result["ancrage_lieu"],
                    agence=result["ancrage_agence"])
        return result

    def extraire(self, image_bytes: bytes,
                 qr_montant: Optional[float] = None) -> dict:
        """
        Extrait les 3 zones manuscrites + compare les montants.

        Paramètres :
          image_bytes : image du chèque en bytes
          qr_montant  : montant QR pecc.tn (référence BCT, prioritaire)

        Retourne :
          {
            "beneficiaire"      : str   | None,
            "montant_chiffres"  : float | None,
            "montant_lettres"   : str   | None,  ← texte OCR brut
            "comparaison"       : {
                "statut"           : CONFORME | FALSIFICATION | OCR_INSUFFISANT,
                "montant_chiffres" : float,
                "montant_lettres"  : float,   ← valeur convertie
                "texte_ocr_brut"   : str,
                "texte_corrige"    : str,
                "detail"           : str,
            },
            "falsification"     : bool,
            "yolo_disponible"   : bool,
            "svm_disponible"    : bool,
          }
        """
        result = {
            "beneficiaire":     None,
            "montant_chiffres": None,
            "montant_lettres":  None,
            "comparaison":      {},
            "falsification":    False,
            "yolo_disponible":  self._yolo is not None,
            "svm_disponible":   self._svm.disponible,
        }

        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            logger.error("phase3_image_illisible")
            return result

        if self._yolo is None:
            logger.warning("phase3_yolo_absent",
                           fallback="ancrage_mots_cles" if _CLEANER_OK else "aucun")
            if _CLEANER_OK:
                return self._extraire_par_ancrage(img, qr_montant, result)
            return result

        debug = Path("debug_crops")
        debug.mkdir(exist_ok=True)

        # ── Inférence YOLO Phase 3 ──────────────────────────────────────
        try:
            yolo_res = self._yolo(img, conf=0.25, verbose=False)[0]
        except Exception as e:
            logger.error("yolo_p3_inference_erreur", error=str(e))
            return result

        logger.info("yolo_p3_zones_detectees", n=len(yolo_res.boxes))

        # Garder la meilleure détection par classe (conf la plus haute)
        meilleures: dict = {}
        for box in yolo_res.boxes:
            cls_id = int(box.cls[0])
            conf   = float(box.conf[0])
            if cls_id not in CLASSES_P3:
                continue
            nom = CLASSES_P3[cls_id]
            if nom not in meilleures or conf > meilleures[nom]["conf"]:
                meilleures[nom] = {"conf": conf, "box": box}

        # ── OCR sur chaque zone ─────────────────────────────────────────
        for nom, info in meilleures.items():
            xyxy = info["box"].xyxy[0].tolist()
            h, w = img.shape[:2]
            pad  = 8
            crop = img[
                max(0, int(xyxy[1])-pad):min(h, int(xyxy[3])+pad),
                max(0, int(xyxy[0])-pad):min(w, int(xyxy[2])+pad)
            ]
            if crop.size == 0:
                continue

            cv2.imwrite(str(debug / f"p3_{nom}.jpg"), crop)

            if nom == "beneficiaire":
                texte_b = _ocr_crop(crop)
                result["beneficiaire"] = _nettoyer_beneficiaire(texte_b)
                logger.debug("p3_beneficiaire", brut=texte_b,
                             propre=result["beneficiaire"])

            elif nom == "montant_chiffres":
                texte  = _ocr_crop(crop)
                result["montant_chiffres"] = _extraire_montant_chiffres(texte)
                logger.debug("p3_montant_chiffres",
                             texte=texte, val=result["montant_chiffres"])

            elif nom == "montant_lettres":
                texte = self._lire_montant_lettres(crop)
                result["montant_lettres"] = texte
                logger.debug("p3_montant_lettres", texte=texte[:80])

        # ── Comparaison des montants ────────────────────────────────────
        # Priorité : QR montant (signé BCT) > montant_chiffres OCR
        montant_ref = qr_montant if qr_montant is not None \
            else result["montant_chiffres"]

        if result["montant_lettres"] and montant_ref is not None:
            result["comparaison"] = comparer_montants(
                montant_ref, result["montant_lettres"])
            result["falsification"] = \
                result["comparaison"].get("statut") == "FALSIFICATION"
        elif result["montant_lettres"]:
            result["comparaison"] = {
                "statut": "OCR_INSUFFISANT",
                "detail": "Montant en chiffres non disponible pour comparaison",
            }
        else:
            result["comparaison"] = {
                "statut": "OCR_INSUFFISANT",
                "detail": "Zone montant_lettres non détectée ou vide",
            }

        logger.info("phase3_done",
                    beneficiaire     = result["beneficiaire"],
                    montant_chiffres = result["montant_chiffres"],
                    montant_lettres  = result["montant_lettres"],
                    statut           = result["comparaison"].get("statut","—"),
                    falsification    = result["falsification"])
        return result


# ══════════════════════════════════════════════════════════════════════════
#  MAIN — Tests et utilitaires
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Phase 3 — Zones manuscrites chèques tunisiens")
    parser.add_argument("--tester",        metavar="IMAGE",
                        help="Tester sur une image de chèque")
    parser.add_argument("--entrainer-svm", action="store_true",
                        help="Entraîner le SVM (dataset_svm/ requis)")
    parser.add_argument("--qr-montant",    type=float, default=None,
                        help="Montant QR pecc.tn (référence)")
    args = parser.parse_args()

    if args.entrainer_svm:
        print("Entraînement SVM sur dataset_svm/ ...")
        SVMManuscrit.entrainer()

    elif args.tester:
        if not Path(args.tester).exists():
            print(f"Image introuvable : {args.tester}")
        else:
            p3 = Phase3Manuscrite()
            with open(args.tester, "rb") as f:
                img_bytes = f.read()
            result = p3.extraire(img_bytes, qr_montant=args.qr_montant)

            print()
            print("=" * 60)
            print("  RÉSULTATS PHASE 3")
            print("=" * 60)
            print(f"  YOLO Phase 3  : {'OK' if result['yolo_disponible'] else 'ABSENT'}")
            print(f"  SVM           : {'OK' if result['svm_disponible']  else 'Fallback PaddleOCR'}")
            print()
            print(f"  Bénéficiaire      : {result['beneficiaire']}")
            print(f"  Montant chiffres  : {result['montant_chiffres']}")
            print(f"  Montant lettres   : '{result['montant_lettres']}'")
            print()
            c = result["comparaison"]
            if c:
                print(f"  COMPARAISON :")
                print(f"    Statut          : {c.get('statut','—')}")
                print(f"    Chiffres        : {c.get('montant_chiffres')}")
                print(f"    Lettres (conv.) : {c.get('montant_lettres')}")
                print(f"    Texte brut      : '{c.get('texte_ocr_brut','')}'")
                print(f"    Texte corrigé   : '{c.get('texte_corrige','')}'")
                print(f"    Détail          : {c.get('detail','')}")
                print()
                statut = c.get("statut","")
                if   statut == "CONFORME":
                    print("  ✓ CHÈQUE CONFORME")
                elif statut == "FALSIFICATION":
                    print("  ✗ FALSIFICATION DÉTECTÉE")
                else:
                    print("  ? VÉRIFICATION MANUELLE REQUISE")

    else:
        # Test de conversion lettres → nombres (sans image)
        print()
        print("=" * 60)
        print("  TEST CONVERSION + EXTRACTION")
        print("=" * 60)
        print()

        # Test extraction montant_chiffres
        print("  Montant chiffres :")
        cas_c = [
            ("BPD # 5000 #",      5000.0),
            ("BPD # 5 000 #",     5000.0),
            ("BPD # 5.000 #",     5000.0),
            ("5000",               5000.0),
            ("5 000",              5000.0),
            ("250",                 250.0),
            ("",                     None),
        ]
        ok1 = 0
        for texte, att in cas_c:
            res  = _extraire_montant_chiffres(texte)
            flag = res == att
            if flag: ok1 += 1
            print("    {} {:25s} → {}".format("OK" if flag else "FAIL",
                                              repr(texte), res))
        print(f"    {ok1}/{len(cas_c)} OK\n")

        # Test nettoyage bénéficiaire
        print("  Bénéficiaire :")
        cas_b = [
            ("A l'ordre de M. Ahmed",  "M. Ahmed"),
            ("A l'ordre de Sté XYZ",   "Sté XYZ"),
            ("لامر Ahmed Ben Ali",      "Ahmed Ben Ali"),
            ("M. Ahmed",               "M. Ahmed"),
            ("",                        None),
        ]
        ok2 = 0
        for texte, att in cas_b:
            res  = _nettoyer_beneficiaire(texte)
            flag = res == att
            if flag: ok2 += 1
            print("    {} {:35s} → {}".format("OK" if flag else "FAIL",
                                              repr(texte[:35]), repr(res)))
        print(f"    {ok2}/{len(cas_b)} OK\n")

        # Test conversion lettres → nombres
        print("  Conversion lettres → nombres :")
        cas_l = [
            ("cinq mille dinars",            5000.0),
            ("deux cent cinquante dinars",    250.0),
            ("mille cinq cents",             1500.0),
            ("trois mille deux cents",       3200.0),
            ("vingt dinars",                   20.0),
            ("cent dinars",                   100.0),
            ("cinqs mille dinars",           5000.0),   # faute OCR
            ("veingt dinars",                  20.0),   # faute OCR
            ("5000",                         5000.0),   # OCR direct
        ]
        ok3 = 0
        for texte, att in cas_l:
            res  = convertir_lettres_vers_nombre(texte)
            flag = res is not None and abs(res - att) < 0.1
            if flag: ok3 += 1
            print("    {} {:40s} → {}".format("OK" if flag else "FAIL",
                                              texte[:40], res))
        print(f"    {ok3}/{len(cas_l)} OK\n")

        # Test comparaison
        print("  Comparaison montants :")
        c1 = comparer_montants(5000.0, "cinq mille dinars")
        c2 = comparer_montants(5000.0, "deux mille dinars")
        c3 = comparer_montants(None,   "cinq mille dinars")
        print(f"    {c1['statut']:<15} — {c1['detail']}")
        print(f"    {c2['statut']:<15} — {c2['detail']}")
        print(f"    {c3['statut']:<15} — {c3['detail']}")
        print()

        total = ok1 + ok2 + ok3
        total_max = len(cas_c) + len(cas_b) + len(cas_l)
        print(f"  SCORE TOTAL : {total}/{total_max} OK")