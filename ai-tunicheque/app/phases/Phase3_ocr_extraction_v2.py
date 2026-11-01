"""
app/phases/Phase3_ocr_extraction_v2.py
═══════════════════════════════════════════════════════════════════════
Phase 3 — Extraction COMPLÈTE des données manuscrites

CORRECTIONS v3.0 :
  ✅ FIX 1 : PaddleOCR Singleton → chargement UNIQUE (pas à chaque appel)
  ✅ FIX 2 : parse_amount → cherche d'abord dans #...# (évite "3 BE° #1652,824#" → 31652)
  ✅ FIX 3 : Montant lettres → filtre texte imprimé (payez/non endossable/les chèques...)
  ✅ FIX 4 : Bénéficiaire → filtre numéros de chèque et textes imprimés
  ✅ FIX 5 : Performance → early stop OCR.Space haute conf, PaddleOCR lazy load

OBJECTIF :
  ① Montant en chiffres → OBLIGATOIRE (cascade OCR)
  ② Montant en lettres  → auto-généré depuis ① + agent vérifie
  ③ Bénéficiaire        → PaddleOCR + nettoyage
  ④ Date                → PaddleOCR + nettoyage
"""

import asyncio, base64, difflib, os, re, time
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List

import cv2, numpy as np, requests

# ═══════════════════════════════════════════════════════════════
# IMPORTS PIPELINE
# ═══════════════════════════════════════════════════════════════

try:
    from app.models.pipeline_models import PhaseResult
except ImportError:
    from dataclasses import dataclass, field
    @dataclass
    class PhaseResult:
        phase: str = "ocr"; score: float = 0.0; passed: bool = False
        duration_ms: int = 0; details: Dict[str, Any] = field(default_factory=dict)

try:
    import structlog; logger = structlog.get_logger()
except ImportError:
    import logging
    class _L:
        def __init__(self): self._l = logging.getLogger("phase3")
        def info(self, m, **k):    self._l.info(m)
        def warning(self, m, **k): self._l.warning(m)
        def error(self, m, **k):   self._l.error(m)
    logger = _L()


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

OCRSPACE_KEY   = os.getenv("OCRSPACE_API_KEY",   "helloworld")
OCRSPACE_URL   = "https://api.ocr.space/parse/image"
YOLO_MONTANT   = os.getenv("YOLO_MONTANT_PATH",
                           "saved_models/yolo_montant/yolo_montant_best.pt")
YOLO_PHASE3    = os.getenv("YOLO_PHASE3_PATH",
                           "saved_models/yolo_ocr/best_v24.pt")
YOLO_TIREUR    = os.getenv("YOLO_TIREUR_PATH",   "saved_models/yolo_tireur/best_tireur.pt")
YOLO_DATELIEU  = os.getenv("YOLO_DATELIEU_PATH", "saved_models/yolo_datelieu/best_datelieu.pt")
YOLO_BENEF     = os.getenv("YOLO_BENEF_PATH",    "saved_models/yolo_benef/best_beneficiaire.pt")
YOLO_AGENCE    = os.getenv("YOLO_AGENCE_PATH",   "saved_models/yolo_agence/best.pt")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
GEMINI_KEY     = os.getenv("GEMINI_API_KEY",     "")
MISTRAL_KEY    = os.getenv("MISTRAL_API_KEY",    "")

YOLO_CONF      = 0.25   # seuil général (montant, agence, phase3)
YOLO_CONF_SPEC = 0.08   # seuil abaissé pour modèles spécialisés (peu d'images)
MIN_SCORE = 0.55
TIMEOUT   = 8

# Classes YOLO Phase3 (best_v24.pt)
FIELD_NAMES = {
    0: "montant_chiffres", 1: "montant_lettres",
    2: "beneficiaire",     3: "date_lieu",
    4: "signature",        5: "rib",
    6: "num_cheque",       7: "cmc7",
    8: "titulaire",        9: "banque",
    10: "qr_code",         11: "date_expiration",
    12: "montant_max",
}

# ✅ FIX 3 : Textes IMPRIMÉS à éliminer des zones manuscrites
PRINTED_PATTERNS = [
    r"payez\s+contre\s+ce\s+ch[eè]que[^\n]*",
    r"les\s+ch[eè]ques\s+certifi[eé]s[^\n]*",
    r"non\s+endossable[^\n]*",
    r"sauf\s+au\s+profit[^\n]*",
    r"montant\s+max[^\n]*",
    r"valeur\s+maximale[^\n]*",
    r"[aà]\s+l['']ordre\s+de[^\n]*",
    r"la\s+somme\s+de[^\n]*",
    r"ادفعوا[^\n]*",
    r"contre\s+ce\s+ch[eè]que[^\n]*",
    r"ce\s+vnaaeo[^\n]*",
    r"vmoniant[^\n]*",
    r"concern[eé]s[^\n]*",
    r"assimil[eé][^\n]*",
]

# ✅ FIX 4 : Patterns cheque imprimé dans le bénéficiaire
CHEQUE_PRINTED_PATTERNS = [
    r"ch[eè]que\s+n[°o]?\s*\d+",
    r"chèque\s+n[°o]?\s*\d+",
    r"n[°o]?\s*\d{6,}",
    r"\d{7,}",          # long numéros = numéro de chèque
    r"jacaln",          # bruit OCR connu
    r"sacshal",         # bruit OCR connu
    r"chequen[°o]?\d+", # format compact
]


# ═══════════════════════════════════════════════════════════════
# SINGLETON PADDLEOCR
# ═══════════════════════════════════════════════════════════════

_PADDLE_INSTANCE = None

def get_paddle():
    """
    ✅ FIX 1 : Singleton PaddleOCR
    Chargé UNE SEULE FOIS pour tout le processus
    (Évite 2 minutes de chargement à chaque requête)
    """
    global _PADDLE_INSTANCE
    if _PADDLE_INSTANCE is None:
        try:
            from paddleocr import PaddleOCR
            _PADDLE_INSTANCE = PaddleOCR(
                use_angle_cls=True, lang="fr",
                use_gpu=False, show_log=False,
                enable_mkldnn=False
            )
            logger.info("PaddleOCR singleton créé")
        except Exception as e:
            logger.warning(f"PaddleOCR indisponible : {e}")
    return _PADDLE_INSTANCE


# ═══════════════════════════════════════════════════════════════
# UTILITAIRES IMAGE
# ═══════════════════════════════════════════════════════════════

def preprocess(image: np.ndarray) -> np.ndarray:
    """Améliorer image avant OCR"""
    if image is None or image.size == 0:
        return image
    h, w = image.shape[:2]
    if w < 600:
        image = cv2.resize(image, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe    = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.bilateralFilter(enhanced, 5, 75, 75)
    return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)


def to_b64(image: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 95])
    return base64.b64encode(buf.tobytes()).decode("utf-8")


# ═══════════════════════════════════════════════════════════════
# MONTANT EN LETTRES — Génération automatique
# ═══════════════════════════════════════════════════════════════

def _num2words_fr(n: float) -> str:
    """958.5 → 'neuf cent cinquante-huit dinars et cinq cents millimes'"""
    try:
        if n <= 0: return ""
        integer_part = int(n)
        decimal_part = int(round((n % 1) * 1000))

        units = ["","un","deux","trois","quatre","cinq","six","sept","huit","neuf"]
        teens = ["dix","onze","douze","treize","quatorze","quinze","seize",
                 "dix-sept","dix-huit","dix-neuf"]
        tens  = ["","dix","vingt","trente","quarante","cinquante","soixante",
                 "","quatre-vingt","quatre-vingt-dix"]

        def to_w(num: int) -> str:
            if num == 0: return ""
            if num < 10: return units[num]
            if num < 20: return teens[num - 10]
            if num < 100:
                t, u = num // 10, num % 10
                if u == 0:
                    return tens[t] + ("s" if t == 8 else "")
                if t == 7: return "soixante-" + to_w(10 + u)
                if t in (8, 9): return "quatre-vingt" + ("-" + to_w(num % 20 if t==9 else u) if num % 20 else ("s" if t==8 else ""))
                return tens[t] + "-" + to_w(u)
            if num < 1000:
                h, rest = num // 100, num % 100
                p = ("cent" if h == 1 else units[h] + " cent")
                return p + ("s" if h > 1 and rest == 0 else (" " + to_w(rest) if rest else ""))
            th, rest = num // 1000, num % 1000
            p = "mille" if th == 1 else to_w(th) + " mille"
            return p + (" " + to_w(rest) if rest else "")

        result = to_w(integer_part) + " dinars"
        if decimal_part > 0:
            result += " et " + to_w(decimal_part) + " millimes"
        return result.strip()
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════
# POST-PROCESSING MONTANT EN CHIFFRES
# ═══════════════════════════════════════════════════════════════

def parse_amount(text: str) -> Tuple[Optional[float], float]:
    """
    ✅ FIX 2 : Extraire montant depuis texte OCR

    Stratégie :
      1. Chercher d'abord entre # ... # (format chèque tunisien)
         Ex: "3 BE° #1652°,824#*" → cherche dans #1652°,824# → 1652.824
      2. Sinon chercher le meilleur pattern dans le texte entier
    """
    if not text:
        return None, 0.0

    text = str(text).strip()

    # ✅ FIX 2 : Priorité aux nombres entre # ... #
    hash_match = re.search(r"#\s*([0-9][0-9\s,°.]*)\s*#", text)
    if hash_match:
        inner = hash_match.group(1)
        inner = re.sub(r"[°\s]", "", inner)   # Supprimer ° et espaces
        inner = inner.replace(",", ".")
        # Nettoyer doubles points
        inner = re.sub(r"\.+", ".", inner)
        try:
            amount = float(inner)
            if 0.1 <= amount <= 500_000:
                return amount, 0.98
        except ValueError:
            pass

    # Fallback : chercher dans texte nettoyé
    cleaned = re.sub(r"[^\d.,]", "", text)
    if not cleaned:
        return None, 0.0

    patterns = [
        (r"(\d{1,5})[,.](\d{3})", 0.95),
        (r"(\d{1,5})[,.](\d{2})",  0.90),
        (r"(\d{1,5})[,.](\d{1})",  0.85),
        (r"(\d{4,6})",              0.75),
        (r"(\d{2,3})",              0.65),
    ]
    for pattern, conf in patterns:
        for m in re.finditer(pattern, cleaned):
            try:
                amount = float(m.group(0).replace(",", "."))
                if 0.1 <= amount <= 500_000:
                    return amount, conf
            except ValueError:
                continue

    return None, 0.0


def score_result(amount, text, api_conf):
    if amount is None: return 0.0
    _, p = parse_amount(text)
    return round(min(1.0, api_conf * 0.5 + p * 0.5), 3)


# ═══════════════════════════════════════════════════════════════
# NETTOYAGE DES CHAMPS TEXTE
# ═══════════════════════════════════════════════════════════════

def clean_montant_lettres(text: str) -> str:
    """
    ✅ FIX 3 : Supprimer les textes IMPRIMÉS des chèques
    qui parasitent la zone montant_lettres manuscrite

    Garde seulement les mots qui ressemblent à des nombres en lettres
    """
    if not text:
        return ""

    text_lower = text.lower()

    # Supprimer les phrases imprimées connues
    for pat in PRINTED_PATTERNS:
        text_lower = re.sub(pat, " ", text_lower, flags=re.IGNORECASE)

    # Garder seulement les mots du vocabulaire bancaire pertinents
    VALID_WORDS = {
        "un","une","deux","trois","quatre","cinq","six","sept","huit","neuf",
        "dix","onze","douze","treize","quatorze","quinze","seize",
        "dix-sept","dix-huit","dix-neuf","vingt","trente","quarante","cinquante",
        "soixante","soixante-dix","quatre-vingt","quatre-vingt-dix",
        "cent","cents","mille","dinar","dinars","millime","millimes","et",
        # Arabe
        "ألف","مائة","دينار","دنانير","مليم","واحد","اثنان"
    }

    words = text_lower.split()
    valid = [w for w in words if w in VALID_WORDS]

    if len(valid) >= 2:
        return " ".join(valid)

    # Si moins de 2 mots valides → zone vide/illisible
    return ""


def clean_beneficiaire(text: str) -> str:
    """
    Nettoyer le bénéficiaire — supprimer texte imprimé et bruit OCR.
    """
    if not text:
        return ""

    t = text.strip()
    t_lower = t.lower()

    # Mots-clés imprimés qui indiquent qu'on est hors zone manuscrite
    REJECT_KEYWORDS = [
        "payable", "ordrede", "al'ordrede", "a l'ordre",
        "à l'ordre", "l'ordrede", "lwrsiamet",
        "signature", "signe", "sig.",
        "non endossable", "payez", "contre ce",
        "vmoniant", "vnaaeo",
        # YOLO-Benef pointe parfois la zone titulaire → rejeter
        "titulaire", "titulalte", "titulair", "du compte", "comptekt",
        "stamtutels", "syctasx",
    ]
    for kw in REJECT_KEYWORDS:
        if kw in t_lower:
            return ""

    # Trop de points — seuil relevé à 0.22 (cursif produit des points parasites)
    dot_ratio = t.count(".") / max(len(t), 1)
    if dot_ratio > 0.22:
        return ""
    # Nettoyer les points isolés entre lettres : "B.en" → "Ben"
    t = re.sub(r'(?<=[A-Za-zÀ-ÿ])\.(?=[A-Za-zÀ-ÿ])', '', t).strip()

    # Mots très courts séparés par des points → bruit ("Mm.as.s.oo")
    words = t.split()
    short_word_ratio = sum(1 for w in words if len(w.strip(".")) <= 2) / max(len(words), 1)
    if short_word_ratio > 0.5 and len(words) > 2:
        return ""

    # Supprimer préfixes imprimés
    prefixes = [
        r"^[Aa]\s*l['']?\s*ordre\s*de\s*",
        r"^[Àà]\s*l[ée]?\s*ordre\s*de\s*",
        r"^À\s*l'ordre\s*de\s*",
        r"^لامر\s*",
        r"^ل\s*أمر\s*",
    ]
    for pat in prefixes:
        t = re.sub(pat, "", t, flags=re.IGNORECASE).strip()

    # Vérifier si c'est un numéro de chèque ou texte imprimé
    for pat in CHEQUE_PRINTED_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return ""

    # Trop de chiffres ou trop court — seuil relevé à 0.50 (cursif confondu avec chiffres)
    digits_ratio = sum(c.isdigit() for c in t) / max(len(t), 1)
    if digits_ratio > 0.50 or len(t) < 3:
        return ""

    # CamelCase : OCR cursif produit des majuscules aléatoires → normaliser, pas rejeter
    camel = len(re.findall(r'[a-z][A-Z]', t))
    if camel > max(1, len(t.split())):
        t = t.upper()

    return t.upper().strip()


def clean_date(text: str) -> str:
    """Extraire date au format JJ/MM/AAAA"""
    if not text:
        return ""
    m = re.search(r"(\d{2})[/\-.](\d{2})[/\-.](\d{4})", text)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return ""


def clean_lieu(text: str) -> str:
    """Extraire le lieu (ville) de la zone date_lieu — supprime la date, garde le texte."""
    if not text:
        return ""
    t = re.sub(r"\d{2}[/\-.]\d{2}[/\-.]\d{4}", "", text)
    t = re.sub(r"\d{2}[/\-.]\d{2}[/\-.]\d{2}", "", t)
    t = re.sub(r"\b\d{1,2}\b", "", t)
    t = re.sub(r"[,;:.|]", " ", t)
    # Supprimer mots de la zone signature (bruit OCR si mauvaise détection)
    t = re.sub(r'\b[Ss]ignat\w*\b', '', t)
    # Supprimer codes techniques et bruits OCR mélangés lettres/chiffres
    t = re.sub(r'\b[A-Za-z]{1,3}\d[A-Za-z]{1,3}\b', '', t)
    t = re.sub(r'\bCS\b|\bBPD\b|\bACS\b', '', t, flags=re.IGNORECASE)
    # Supprimer chaînes cursives illisibles (≥3 transitions minusc→majusc dans un seul mot)
    filtered = []
    for word in t.split():
        camel = len(re.findall(r'[a-z][A-Z]', word))
        if camel >= 2:
            continue
        filtered.append(word)
    t = " ".join(filtered).strip()
    return t if len(t) >= 2 else ""


# ── Liste INS des villes/quartiers tunisiens pour correction OCR ──────────────
TUNISIAN_CITIES = sorted([
    # Gouvernorats et chefs-lieux
    "TUNIS", "ARIANA", "BEN AROUS", "MANOUBA", "NABEUL", "ZAGHOUAN",
    "BIZERTE", "BEJA", "JENDOUBA", "KEF", "SILIANA",
    "SOUSSE", "MONASTIR", "MAHDIA", "SFAX", "KAIROUAN",
    "KASSERINE", "SIDI BOUZID", "GABES", "MEDENINE", "TATAOUINE",
    "GAFSA", "TOZEUR", "KEBILI",
    # Grand Tunis — quartiers et villes satellites
    "LA MARSA", "CARTHAGE", "SIDI BOU SAID", "GAMMARTH", "RAOUED",
    "LA SOUKRA", "GHAZELA", "ETTADHAMEN", "BARDO", "ENNASR",
    "EL MENZAH", "CHARGUIA", "MANAR", "CITE OLYMPIQUE", "BELVEDERE",
    "LAFAYETTE", "MONTPLAISIR", "CENTRE VILLE", "MEGRINE", "RADES",
    "HAMMAM LIF", "HAMMAM CHOTT", "BOUCHOUCHA", "MOUROUJ", "EZZOUHOUR",
    "EL OMRANE", "BELHASSEN", "BHAR LAZREG", "MENZAH",
    # Villes régionales importantes
    "HAMMAMET", "KELIBIA", "GROMBALIA", "MENZEL BOURGUIBA", "MATEUR",
    "TABARKA", "KRIB", "SBEITLA", "FERIANA", "EL JEM", "CHEBBA",
    "MSAKEN", "KALAA KEBIRA", "KSAR HELLAL", "MOKNINE", "DJEBENIANA",
    "SAKIET EZZIT", "METLAOUI", "NEFTA", "DEGACHE", "HOUMT SOUK",
    "DJERBA", "ZARZIS", "BEN GARDANE", "DOUZ", "REMADA",
    # Termes bancaires courants
    "CENTRE COMMERCIAL", "ZONE INDUSTRIELLE", "ZONE FRANCHE",
    "POLE TECHNOLOGIQUE", "TECHNOPOLE",
])


def _correct_city_token(word: str, cutoff: float = 0.65) -> str:
    """
    Corrige un mot (potentiel nom de ville) par correspondance floue
    contre TUNISIAN_CITIES via difflib (approximation Levenshtein).
    Retourne le mot corrigé, ou le mot original si aucune correspondance.
    """
    w = word.upper().strip()
    if len(w) < 3:
        return word
    matches = difflib.get_close_matches(w, TUNISIAN_CITIES, n=1, cutoff=cutoff)
    return matches[0] if matches else word


def clean_agence(text: str) -> str:
    """
    Extraire le nom d'agence depuis le bloc 'Payable à / يدفع بـ'.
    Garde la ligne qui contient 'AGENCE' ou la première ligne significative.
    """
    if not text:
        return ""
    # Supprimer préfixe "Payable à" et variantes OCR
    t = re.sub(r"^payable\s*[aà]?\s*", "", text.strip(), flags=re.IGNORECASE)
    t = re.sub(r"^يدفع\s*بـ?\s*", "", t, flags=re.IGNORECASE).strip()

    # Supprimer les codes externes à droite de la case agence
    # (SPS, STIMEC et variantes selon les banques — pas une règle fixe)
    t = re.sub(r"\b(?:SPS|STIMEC|CODEA?|REF)\s*[.\-]?\s*\d+\b", "", t,
               flags=re.IGNORECASE)
    # Supprimer les codes alphanumériques isolés type "SPS.71295900"
    t = re.sub(r"\b[A-Z]{2,6}\.?\d{5,}\b", "", t).strip()

    lines = [l.strip() for l in re.split(r"[\n\r\|]+", t) if l.strip()]

    # Chargement unique du correcteur français (silencieux si absent)
    try:
        from spellchecker import SpellChecker as _SC
        _spell_fr = _SC(language='fr')
    except Exception:
        _spell_fr = None

    def _fix_spaces(s: str) -> str:
        """Réintroduire les espaces entre mots collés (artefact OCR)
        + corriger les lettres isolées via dictionnaire français."""
        # 1. Insérer espace entre minuscule→majuscule (mots collés type "RDCBloca")
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = re.sub(r"([A-Za-z])([A-Z]{2,})", r"\1 \2", s)
        # 2. Fix pattern OCR courant : "E T EL:" ou "TE L:" → "TEL:"
        s = re.sub(r'\b[EÉe]\s+T\s+[Ee][Ll]\s*:', 'TEL:', s, flags=re.IGNORECASE)
        s = re.sub(r'\bT[Ee]\s+[Ll]\s*:', 'TEL:', s, flags=re.IGNORECASE)
        # 3. Normaliser espaces multiples
        s = re.sub(r"\s{2,}", " ", s).strip()
        # 4. Reconstruction par dictionnaire français : fusionner lettre isolée + suivant
        if _spell_fr:
            tokens = s.split()
            rebuilt = []
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if len(tok) <= 2 and tok.isalpha() and i + 1 < len(tokens):
                    nxt = tokens[i + 1]
                    merged = tok + nxt
                    merged_low = merged.lower()
                    # Fusionner si le token suivant contient un chiffre (code type LAC2)
                    if any(c.isdigit() for c in nxt) or ':' in nxt:
                        rebuilt.append(merged)
                        i += 2
                        continue
                    # Fusionner si le résultat est un mot français valide
                    if merged_low not in _spell_fr.unknown([merged_low]):
                        rebuilt.append(merged.upper())
                        i += 2
                        continue
                    # Fusionner si la correction donne un mot de même longueur
                    corr = _spell_fr.correction(merged_low)
                    if corr and len(corr) == len(merged_low):
                        rebuilt.append(corr.upper())
                        i += 2
                        continue
                rebuilt.append(tok)
                i += 1
            s = ' '.join(rebuilt)
        return s

    def _apply_city_correction(s: str) -> str:
        """Corrige chaque token qui ressemble à un nom de ville (pas un code)."""
        # Tronquer après TEL: ou TELS: — la suite est une adresse, pas le nom d'agence
        s = re.sub(r'\s+T[ÉE]?L\s*:.*$', '', s, flags=re.IGNORECASE).strip()
        # Tronquer après un numéro de téléphone long (8+ chiffres consécutifs)
        s = re.sub(r'\s+\d{8,}.*$', '', s).strip()
        tokens = s.split()
        corrected = []
        for tok in tokens:
            # Appliquer correction uniquement sur mots purement alphabétiques ≥ 4 chars
            if tok.isalpha() and len(tok) >= 4:
                corrected.append(_correct_city_token(tok))
            else:
                corrected.append(tok)
        return " ".join(corrected)

    # Chercher la ligne contenant "AGENCE" (ou "ACENCE" artefact OCR courant)
    agence_lines = []
    for line in lines:
        if re.search(r"A[Gg][Ee][Nn][CcSs][Ee]?", line):
            agence_lines.append(_fix_spaces(line))
        elif agence_lines:
            agence_lines.append(_fix_spaces(line))

    if agence_lines:
        result = " | ".join(agence_lines[:3])[:90]
        return _apply_city_correction(result)

    # Fallback : première ligne non trop numérique
    for line in lines:
        dr = sum(c.isdigit() for c in line) / max(len(line), 1)
        if dr <= 0.4 and len(line) >= 4:
            return _apply_city_correction(_fix_spaces(line)[:60])
    return ""


def clean_tireur(text: str) -> str:
    """Nettoyer le nom du tireur (émetteur du chèque)."""
    if not text:
        return ""
    t = text.strip()
    for pat in CHEQUE_PRINTED_PATTERNS:
        if re.search(pat, t, re.IGNORECASE):
            return ""
    # Supprimer préfixe numérique/décimal (artefact OCR depuis la zone montant adjacente)
    # ex: ".60 GUIZANI RYM Signat" → "GUIZANI RYM"
    t = re.sub(r'^[\d\s.,;:°\-/\\*#]+', '', t).strip()
    # Supprimer mots liés à la signature (bruit OCR zone signature adjacente)
    t = re.sub(r'\b[Ss]ignat\w*\b', '', t)
    t = re.sub(r'\bSIG\b', '', t, flags=re.IGNORECASE)
    # Normaliser espaces multiples
    t = re.sub(r'\s{2,}', ' ', t).strip()
    digits_ratio = sum(c.isdigit() for c in t) / max(len(t), 1)
    if digits_ratio > 0.5 or len(t) < 2:
        return ""
    # Rejeter si pas de vrai mot lisible (ex: "A1.ume.1e16/3/bs" → rejeté)
    clean_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', t)
    long_words  = [w for w in clean_words if len(w) >= 4]
    if not long_words and len(clean_words) < 2:
        return ""
    return t.upper().strip()


# ═══════════════════════════════════════════════════════════════
# CROPS POSITIONNELS — Fallback quand YOLO ne détecte pas
# ═══════════════════════════════════════════════════════════════
# LAYOUT BCT STANDARD — validé sur image réelle (chequeN + chequeR)
#
#  ┌─────────────────────────────────────────────────────────────┐  y
#  │ Logo+QR  │ N° chèque │ Val.Max │  BPD  # MONTANT #         │ 0-28%
#  ├──────────────────────────────────────────────────────────────┤
#  │ Payez contre ce chèque non endossable... (imprimé bilingue) │ 18-28%
#  │ ─────── MONTANT EN LETTRES (manuscrit, 1-3 lignes) ──────── │ 28-55%
#  │ À l'ordre de ── BÉNÉFICIAIRE (manuscrit) ─────────── لأمر   │ 50-63%
#  ├──────────────┬───────────────────────────┬──────────────────┤
#  │ Payable à    │  Titulaire du compte       │  Signature (s)   │ 60-85%
#  │ AGENCE ...   │  Bq Ag Compte  Clé         │                  │
#  │ Adresse      │  NOM TIREUR (imprimé)      │  [zone vide ou   │
#  │ Tel: ...     │  À VILLE, le JJ/MM/AAAA    │   manuscrite]    │
#  │ x: 0-22%     │  x: 22-65%                 │  x: 65-100%      │
#  ├──────────────┴───────────────────────────┴──────────────────┤
#  │              Date d'expiration JJ/MM/AAAA  (imprimé)        │ 83-92%
#  │              CMC7 (piste magnétique)                         │ 92-100%
#  └─────────────────────────────────────────────────────────────┘
#
# Ces proportions s'appliquent à TOUTES les banques tunisiennes BCT.
# Écart inter-banques : ±5% sur y, ±3% sur x.
# ═══════════════════════════════════════════════════════════════

def _crop_positional_montant(image: np.ndarray) -> np.ndarray:
    """Montant en chiffres — top-right, entre les gardes #...# BCT.
    y=10-26% : exclut la ligne d'en-tête (N° chèque, logo) → cible la ligne # MONTANT #."""
    h, w = image.shape[:2]
    return image[int(h*0.10):int(h*0.26), int(w*0.62):int(w*0.99)]


def _preprocess_montant(image: np.ndarray) -> np.ndarray:
    """Prétraitement haute résolution pour la zone montant.
    Force agrandissement 3× pour améliorer la lecture des chiffres manuscrits par OCR.Space."""
    if image is None or image.size == 0:
        return image
    h, w = image.shape[:2]
    # Agrandir à au moins 300px de haut pour que les chiffres soient lisibles
    scale = max(300 / max(h, 1), 1.5)
    image = cv2.resize(image, (int(w * scale), int(h * scale)),
                       interpolation=cv2.INTER_CUBIC)
    gray     = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    clahe    = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.bilateralFilter(enhanced, 5, 75, 75)
    return cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)


def _crop_positional_benef(image: np.ndarray) -> np.ndarray:
    """Bénéficiaire — ligne 'À l'ordre de', variable selon nb lignes lettres."""
    h, w = image.shape[:2]
    return image[int(h*0.48):int(h*0.65), int(w*0.10):int(w*0.85)]


def _crop_positional_datelieu(image: np.ndarray) -> np.ndarray:
    """Date + Lieu — DANS le bloc Titulaire, partie basse du bloc central.
    Limité à y<82% pour éviter la zone date d'expiration imprimée (y=83-92%)."""
    h, w = image.shape[:2]
    return image[int(h*0.70):int(h*0.82), int(w*0.20):int(w*0.65)]


def _crop_positional_tireur(image: np.ndarray) -> np.ndarray:
    """Nom du tireur — bloc Titulaire central, partie haute."""
    h, w = image.shape[:2]
    return image[int(h*0.58):int(h*0.75), int(w*0.20):int(w*0.65)]


def _crop_positional_agence(image: np.ndarray) -> np.ndarray:
    """Agence — boîte bas-gauche 'Payable à'."""
    h, w = image.shape[:2]
    return image[int(h*0.58):int(h*0.88), int(w*0.00):int(w*0.23)]


# ═══════════════════════════════════════════════════════════════
# EXTRACTION PAR CONTEXTE — ancrage sur labels BCT imprimés
# ═══════════════════════════════════════════════════════════════

def _extract_by_context(image: np.ndarray) -> dict:
    """
    Extraction intelligente par ancrage sur les labels BCT standardisés.

    Stratégie senior :
      Les labels imprimés sont identiques sur TOUS les chèques tunisiens
      (bilingues FR/AR — imposés par la BCT) :
        # ... #           → montant en chiffres
        'À l'ordre de'    → bénéficiaire
        'À VILLE, le'     → date + lieu
        'Payable à'       → agence
        nom dans titulaire → tireur

      On fait UN seul OCR pleine image → on cherche le texte manuscrit
      juste après chaque label imprimé par regex.
      Fonctionne pour n'importe quelle banque tunisienne.
    """
    result: dict = {}

    # ── OCR unique sur l'image entière ──────────────────────────────────
    full_text = ""
    ocr = get_paddle()
    if ocr:
        try:
            res = ocr.ocr(preprocess(image), cls=True)
            if res and res[0]:
                full_text = "\n".join(str(r[1][0]) for r in res[0] if r)
        except Exception:
            pass
    if not full_text:
        full_text = _ocrspace(image).get("text", "")
    if not full_text:
        return result

    # ── 1. Montant en chiffres : # ... # (BCT obligatoire) ──────────────
    m = re.search(r"#\s*([\d\s,\.]+)\s*#", full_text)
    if m:
        amount, conf = parse_amount(m.group(0))
        if amount and 0.1 <= amount <= 500_000:
            result["montant_chiffres"] = amount

    # ── 2. Bénéficiaire : après 'À l'ordre de' / لأمر ───────────────────
    m = re.search(
        r"[Àa]\s*l[''']?\s*ordre\s*de\s*[-_\.]*\s*(.{2,60}?)(?:\s*[-_\.]{2,}|\s*لأمر|$)",
        full_text, re.IGNORECASE | re.MULTILINE
    )
    if not m:
        m = re.search(r"(?:ordre\s*de|ordrede)\s+(.{2,50})", full_text, re.IGNORECASE)
    if m:
        candidate = clean_beneficiaire(m.group(1).strip())
        if candidate:
            result["beneficiaire"] = candidate

    # ── 3. Date + Lieu : 'À VILLE, le JJ/MM/AAAA' ───────────────────────
    m = re.search(
        r"[Àa]\s+([A-ZÀ-Ža-zà-ž][a-zà-ž]{1,20}),?\s*[Ll]e\s+(\d{1,2}[/\-.]\d{2}[/\-.]\d{2,4})",
        full_text
    )
    if m:
        lieu_raw = m.group(1).strip()
        date_raw = m.group(2).strip()
        result["lieu"] = _correct_city_token(lieu_raw.upper()) if len(lieu_raw) >= 2 else lieu_raw
        result["date"] = clean_date(date_raw)
    else:
        # Chercher date seule — exclure dates proches de "expiration" (bas du chèque, imprimé)
        for m2 in re.finditer(r"\b(\d{2}[/\-.]\d{2}[/\-.]\d{4})\b", full_text):
            ctx_around = full_text[max(0, m2.start()-100):m2.end()+100]
            if re.search(r"expir|validit[eé]|صلاح|انتهاء", ctx_around, re.IGNORECASE):
                continue  # date d'expiration imprimée — ignorer
            d = clean_date(m2.group(1))
            if d:
                result["date"] = d
                break

    # ── 4. Agence : après 'Payable à' / 'يدفع بـ' ───────────────────────
    m = re.search(
        r"[Pp]ayable\s+[àa]\s+(.*?)(?:Tel|TEL|Tél|SPS|STIMEC|\n\n|يدفع|$)",
        full_text, re.IGNORECASE | re.DOTALL
    )
    if m:
        agence_raw = m.group(1).strip()[:120]
        agence_val = clean_agence(agence_raw)
        if agence_val:
            result["agence"] = agence_val

    # ── 5. Tireur : après 'Titulaire du compte / صاحب الحساب' ───────────
    _TITUL_ANCHOR = [
        r'(?:Titulaire\s+du\s+compte|صاحب\s*الحساب)\s*/?\s*(?:صاحب\s*الحساب)?\s*[:\-]?\s*([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-Za-zÀ-ÿ\s\-\.&]{2,60})',
        r'(?:Titulaire\s+du\s+compte|صاحب\s*الحساب)\s*/?\s*(?:صاحب\s*الحساب)?\s*[:\-]?\s*\n\s*([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-Za-zÀ-ÿ\s\-\.&]{2,60})',
    ]
    for pat in _TITUL_ANCHOR:
        m = re.search(pat, full_text, re.IGNORECASE | re.MULTILINE)
        if m:
            candidate = clean_tireur(m.group(1).strip())
            if candidate and len(candidate) >= 3:
                result["tireur"] = candidate
                break

    return result


# ═══════════════════════════════════════════════════════════════
# YOLO DETECTOR
# ═══════════════════════════════════════════════════════════════

class YOLODetector:
    def __init__(self, model_path: str, name: str = "YOLO"):
        self.model = None
        self.name  = name
        if not Path(model_path).exists():
            logger.warning(f"{name} non trouvé : {model_path}")
            return
        try:
            from ultralytics import YOLO
            self.model = YOLO(model_path)
            logger.info(f"{name} chargé : {Path(model_path).name}")
        except Exception as e:
            logger.warning(f"{name} erreur : {e}")

    def crop_best(self, image, conf=YOLO_CONF, y_range=(0.0, 1.0)):
        """Crop la zone avec meilleure confiance.
        y_range : (min%, max%) en fraction de hauteur — filtre les fausses détections hors-zone.
        """
        if self.model is None:
            return image, None, 0.0
        try:
            results = self.model(image, conf=conf, verbose=False)
            if not results or not results[0].boxes:
                return image, None, 0.0
            boxes = results[0].boxes
            h, w  = image.shape[:2]
            y_min_px, y_max_px = y_range[0] * h, y_range[1] * h

            # Filtrer par position verticale puis garder la meilleure confiance
            valid = [
                (i, float(boxes.conf[i]))
                for i in range(len(boxes))
                if y_min_px <= (boxes.xyxy[i][1] + boxes.xyxy[i][3]).item() / 2 <= y_max_px
            ]
            if not valid:
                return image, None, 0.0
            best_idx = max(valid, key=lambda t: t[1])[0]

            x1, y1, x2, y2 = [int(v) for v in boxes.xyxy[best_idx].tolist()]
            yc = float(boxes.conf[best_idx].item())
            m  = 8
            x1, y1 = max(0, x1-m), max(0, y1-m)
            x2, y2 = min(w, x2+m), min(h, y2+m)
            return image[y1:y2, x1:x2], {"x1":x1,"y1":y1,"x2":x2,"y2":y2}, yc
        except Exception as e:
            logger.error(f"YOLO crop : {e}")
            return image, None, 0.0

    def detect_all_fields(self, image, field_names=FIELD_NAMES, conf=YOLO_CONF):
        """Détecter toutes les zones manuscrites"""
        crops = {}
        if self.model is None:
            return crops
        try:
            results = self.model(image, conf=conf, verbose=False)
            if not results:
                return crops
            h, w = image.shape[:2]
            best = {}
            for box in results[0].boxes:
                cls_id = int(box.cls[0])
                bc = float(box.conf[0])
                if cls_id not in field_names:
                    continue
                if cls_id not in best or bc > best[cls_id]["conf"]:
                    best[cls_id] = {"conf": bc, "box": box}
            for cls_id, info in best.items():
                field = field_names[cls_id]
                x1, y1, x2, y2 = [int(v) for v in info["box"].xyxy[0].tolist()]
                pad = 8
                crop = image[max(0,y1-pad):min(h,y2+pad),
                max(0,x1-pad):min(w,x2+pad)]
                if crop.size > 0:
                    crops[field] = crop
        except Exception as e:
            logger.error(f"YOLO detect_all : {e}")
        return crops


# ═══════════════════════════════════════════════════════════════
# OCR — COUCHES CASCADE (montant_chiffres)
# ═══════════════════════════════════════════════════════════════

def _ocrspace(image: np.ndarray, preprocessor=None) -> Dict[str, Any]:
    """Couche 1 : OCR.Space (principal).
    preprocessor : fonction de prétraitement optionnelle (défaut = preprocess standard)."""
    try:
        proc  = preprocessor if preprocessor else preprocess
        img_b64 = to_b64(proc(image))
        payload = {
            "base64Image": f"data:image/jpeg;base64,{img_b64}",
            "apikey":      OCRSPACE_KEY,
            "language":    "fre",
            "OCREngine":   "2",
            "scale":       "true",
        }
        r = requests.post(OCRSPACE_URL, data=payload, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("ParsedResults", [])
        text    = results[0].get("ParsedText", "").strip() if results else ""
        return {"text": text, "conf": 0.82 if text else 0.0}
    except Exception as e:
        logger.warning(f"OCR.Space : {e}")
        return {"text": "", "conf": 0.0}


def _paddle_ocr(image: np.ndarray) -> Dict[str, Any]:
    """Couche 2 : PaddleOCR (singleton)"""
    ocr = get_paddle()
    if ocr is None:
        return {"text": "", "conf": 0.0}
    try:
        results = ocr.ocr(preprocess(image), cls=True)
        if not results or not results[0]:
            return {"text": "", "conf": 0.0}
        texts = [str(r[1][0]) for r in results[0] if r]
        confs = [float(r[1][1]) for r in results[0] if r]
        text  = " ".join(texts).strip()
        conf  = float(np.mean(confs)) if confs else 0.0
        return {"text": text, "conf": conf}
    except Exception as e:
        logger.warning(f"PaddleOCR : {e}")
        return {"text": "", "conf": 0.0}


def _vlm(image: np.ndarray, prompt: str, service: str) -> Dict[str, Any]:
    """Couches 3-5 : VLMs"""
    img_b64 = to_b64(image)
    try:
        if service == "qwen" and OPENROUTER_KEY:
            r = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {OPENROUTER_KEY}","Content-Type":"application/json",
                         "HTTP-Referer":"https://tunicheque.tn"},
                json={"model":"qwen/qwen2.5-vl-72b-instruct:free",
                      "messages":[{"role":"user","content":[
                          {"type":"text","text":prompt},
                          {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{img_b64}"}}
                      ]}],"temperature":0.0,"max_tokens":30},
                timeout=TIMEOUT)
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                return {"text":text,"conf":0.88 if text else 0.0}

        elif service == "gemini" and GEMINI_KEY:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_KEY}",
                headers={"Content-Type":"application/json"},
                json={"contents":[{"parts":[{"text":prompt},
                                            {"inline_data":{"mime_type":"image/jpeg","data":img_b64}}]}],
                      "generationConfig":{"temperature":0.0,"maxOutputTokens":30}},
                timeout=TIMEOUT)
            if r.status_code == 200:
                text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                return {"text":text,"conf":0.90 if text else 0.0}

        elif service == "mistral" and MISTRAL_KEY:
            r = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"},
                json={"model":"pixtral-12b-2409",
                      "messages":[{"role":"user","content":[
                          {"type":"text","text":prompt},
                          {"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{img_b64}"}}
                      ]}],"temperature":0.0,"max_tokens":30},
                timeout=TIMEOUT)
            if r.status_code == 200:
                text = r.json()["choices"][0]["message"]["content"].strip()
                return {"text":text,"conf":0.88 if text else 0.0}
    except Exception as e:
        logger.warning(f"VLM {service} : {e}")
    return {"text":"","conf":0.0}


def _vote(candidates: list) -> Tuple[Optional[float], float]:
    """Consensus entre couches (tolérance 5%)"""
    valides = [c for c in candidates if c["amount"] is not None]
    if not valides:
        return None, 0.0
    if len(valides) == 1:
        return valides[0]["amount"], valides[0]["score"]
    groupes = {}
    for v in valides:
        found = False
        for k in groupes:
            if abs(v["amount"] - k) / max(k, 0.01) < 0.05:
                groupes[k]["count"] += 1
                groupes[k]["score"] = max(groupes[k]["score"], v["score"])
                found = True; break
        if not found:
            groupes[v["amount"]] = {"count":1,"score":v["score"]}
    best_k, best_v = max(groupes.items(), key=lambda x:(x[1]["count"],x[1]["score"]))
    return best_k, round(min(1.0, best_v["score"] + 0.08*(best_v["count"]-1)), 3)


def cascade_montant(image: np.ndarray) -> Tuple[Optional[float], float, str]:
    """Pipeline cascade 5 couches pour montant_chiffres"""
    candidates = []
    PROMPT = ("Tunisian cheque amount zone. Read ONLY the number between # symbols. "
              "Example: '#1652,824#' → reply '1652.824'. Digits only, no text.")

    # C1 : OCR.Space
    print("    [C1] OCR.Space...", end=" ", flush=True)
    r1 = _ocrspace(image)
    a1, _ = parse_amount(r1["text"])
    s1 = score_result(a1, r1["text"], r1["conf"])
    candidates.append({"layer":"OCR.Space","amount":a1,"score":s1})
    print(f"'{r1['text'][:30]}' → {a1} ({s1:.0%})")
    if a1 and s1 >= 0.70:
        return a1, s1, "OCR.Space"

    # C2 : PaddleOCR
    print("    [C2] PaddleOCR...", end=" ", flush=True)
    r2 = _paddle_ocr(image)
    a2, _ = parse_amount(r2["text"])
    s2 = score_result(a2, r2["text"], r2["conf"])
    candidates.append({"layer":"PaddleOCR","amount":a2,"score":s2})
    print(f"'{r2['text'][:30]}' → {a2} ({s2:.0%})")
    best, sc = _vote(candidates)
    if best and sc >= MIN_SCORE:
        return best, sc, "C1+C2"

    # C3 : Qwen
    if OPENROUTER_KEY:
        print("    [C3] Qwen...", end=" ", flush=True)
        r3 = _vlm(image, PROMPT, "qwen")
        a3, _ = parse_amount(r3["text"])
        s3 = score_result(a3, r3["text"], r3["conf"])
        candidates.append({"layer":"Qwen","amount":a3,"score":s3})
        print(f"'{r3['text'][:30]}' → {a3} ({s3:.0%})")
        best, sc = _vote(candidates)
        if best and sc >= MIN_SCORE:
            return best, sc, "Qwen"

    # C4 : Gemini
    if GEMINI_KEY:
        print("    [C4] Gemini...", end=" ", flush=True)
        r4 = _vlm(image, PROMPT, "gemini")
        a4, _ = parse_amount(r4["text"])
        s4 = score_result(a4, r4["text"], r4["conf"])
        candidates.append({"layer":"Gemini","amount":a4,"score":s4})
        print(f"'{r4['text'][:30]}' → {a4} ({s4:.0%})")
        best, sc = _vote(candidates)
        if best and sc >= MIN_SCORE:
            return best, sc, "Gemini"

    # C5 : Mistral
    if MISTRAL_KEY:
        print("    [C5] Mistral...", end=" ", flush=True)
        r5 = _vlm(image, PROMPT, "mistral")
        a5, _ = parse_amount(r5["text"])
        s5 = score_result(a5, r5["text"], r5["conf"])
        candidates.append({"layer":"Mistral","amount":a5,"score":s5})
        print(f"'{r5['text'][:30]}' → {a5} ({s5:.0%})")

    best, sc = _vote(candidates)
    return best, sc, "vote_final"


# ═══════════════════════════════════════════════════════════════
# OCR CHAMP SIMPLE (bénéficiaire, date)
# ═══════════════════════════════════════════════════════════════

def _paddle_ocr_from_x(image: np.ndarray, x_ratio: float = 0.30) -> str:
    """
    PaddleOCR positionnel : ne retourne que le texte dont le centre X
    est à droite de x_ratio * largeur — utile pour ignorer labels imprimés.
    """
    ocr = get_paddle()
    if ocr is None:
        return ""
    try:
        results = ocr.ocr(preprocess(image), cls=True)
        if not results or not results[0]:
            return ""
        w = image.shape[1]
        threshold = w * x_ratio
        parts = []
        for r in results[0]:
            if not r:
                continue
            box = r[0]   # [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
            x_center = (box[0][0] + box[2][0]) / 2
            if x_center >= threshold:
                parts.append(str(r[1][0]))
        return " ".join(parts).strip()
    except Exception:
        return ""


def ocr_field(image: np.ndarray, field: str) -> str:
    """OCR PaddleOCR + fallback OCR.Space"""
    text = ""

    # PaddleOCR d'abord (local, rapide)
    r = _paddle_ocr(image)
    if r["text"] and len(r["text"]) > 2:
        text = r["text"]

    # Fallback OCR.Space si vide
    if not text:
        r2 = _ocrspace(image)
        text = r2["text"]

    # Nettoyage selon champ
    if field == "beneficiaire":
        return clean_beneficiaire(text)
    elif field in ("date", "date_lieu"):
        return clean_date(text)
    elif field == "montant_lettres":
        return clean_montant_lettres(text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# CLASSE PRINCIPALE
# ═══════════════════════════════════════════════════════════════

class OCRPhaseV2:
    """
    Phase 3 COMPLÈTE v3.0 — Extraction données manuscrites

    ① Montant chiffres → Cascade OCR 5 couches (YOLO montant + OCR.Space+...)
    ② Montant lettres  → OCR filtré + auto-généré si difficile
    ③ Bénéficiaire     → YOLO phase3 + PaddleOCR + nettoyage strict
    ④ Date             → YOLO phase3 + PaddleOCR

    FIXES v3.0 :
      ✅ Singleton PaddleOCR (chargement unique, rapide)
      ✅ parse_amount cherche dans #...# en priorité
      ✅ Filtre texte imprimé dans lettres et bénéficiaire
      ✅ Early stop cascade si OCR.Space suffit
    """

    def __init__(self):
        # YOLO montant (binôme)
        self.yolo_montant = YOLODetector(YOLO_MONTANT, "YOLO-Montant")

        # YOLO phase3 (zones manuscrites — fallback général)
        self.yolo_phase3  = YOLODetector(YOLO_PHASE3, "YOLO-Phase3")

        # YOLO spécialisés par champ (entraînés spécifiquement)
        self.yolo_tireur   = YOLODetector(YOLO_TIREUR,   "YOLO-Tireur")
        self.yolo_datelieu = YOLODetector(YOLO_DATELIEU, "YOLO-DateLieu")
        self.yolo_benef    = YOLODetector(YOLO_BENEF,    "YOLO-Benef")
        self.yolo_agence   = YOLODetector(YOLO_AGENCE,   "YOLO-Agence")

        # ✅ FIX 1 : PaddleOCR initialisé au startup (singleton)
        get_paddle()

        # Flags compatibilité main.py
        self.use_paddle  = get_paddle() is not None
        self.use_mistral = bool(MISTRAL_KEY)
        self.use_trocr   = False

        print("\n  ✅ Phase 3 v4.0 (YOLO spécialisés) :")
        print(f"     YOLO Montant  : {'✅' if self.yolo_montant.model else '⚠️'}")
        print(f"     YOLO Phase3   : {'✅' if self.yolo_phase3.model else '⚠️'}")
        print(f"     YOLO Tireur   : {'✅' if self.yolo_tireur.model else '⚠️'}")
        print(f"     YOLO DateLieu : {'✅' if self.yolo_datelieu.model else '⚠️'}")
        print(f"     YOLO Benef    : {'✅' if self.yolo_benef.model else '⚠️'}")
        print(f"     YOLO Agence   : {'✅' if self.yolo_agence.model else '⚠️'}")
        print(f"     PaddleOCR     : {'✅' if self.use_paddle else '❌'}")
        print(f"     OCR.Space     : ✅ key={OCRSPACE_KEY[:10]}...")
        print(f"     Qwen          : {'✅' if OPENROUTER_KEY else '⚠️'}")
        print(f"     Gemini        : {'✅' if GEMINI_KEY else '⚠️'}")
        print(f"     Mistral       : {'✅' if MISTRAL_KEY else '⚠️'}\n")

    async def extract(self, recto_bytes: bytes) -> PhaseResult:
        """Point d'entrée main.py"""
        t0 = time.time()
        try:
            arr   = np.frombuffer(recto_bytes, dtype=np.uint8)
            image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if image is None:
                return self._error("Image illisible", t0)

            extracted = {
                "montant_chiffres":     None,
                "montant_chiffres_str": "",
                "montant_lettres":      None,
                "lettres_source":       None,
                "beneficiaire":         None,
                "date":                 None,
                "lieu":                 None,
                "date_lieu":            None,   # combiné pour report_formatter
                "tireur":               None,
                "titulaire":            None,   # alias tireur pour report_formatter
                "agence":               None,
            }

            # ══════════════════════════════════════════════════
            # ① MONTANT EN CHIFFRES
            # ══════════════════════════════════════════════════
            print("\n  ① Montant en chiffres")

            # C0 : Double OCR sur crop positionnel BCT (zone # MONTANT # standardisée)
            # Crop y=10-26% x=62-99% avec agrandissement 3× → fiable sur toutes banques tunisiennes
            # Cross-validation OCR.Space + PaddleOCR : accord requis pour early-exit
            print("    [C0] Crop positionnel montant (y=10-26%, x=62-99%) + 3× upscale...")
            crop_c0 = _crop_positional_montant(image)
            print(f"        Taille crop : {crop_c0.shape[1]}×{crop_c0.shape[0]} px")

            # C0a : OCR.Space haute résolution
            r_c0a = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _ocrspace(crop_c0, preprocessor=_preprocess_montant))
            a0a, s0a = parse_amount(r_c0a["text"])
            hash_c0a = "#" in r_c0a["text"]
            print(f"    [C0a-OCR.Space]  raw='{r_c0a['text'][:60]}' → {a0a} ({s0a:.0%}) hash={hash_c0a}")

            # C0b : PaddleOCR (cross-validation locale, gratuite)
            r_c0b = await asyncio.get_event_loop().run_in_executor(
                None, lambda: _paddle_ocr(crop_c0))
            a0b, s0b = parse_amount(r_c0b["text"])
            print(f"    [C0b-PaddleOCR]  raw='{r_c0b['text'][:60]}' → {a0b} ({s0b:.0%})")

            montant, m_score, layer = None, 0.0, ""
            bbox_m, yolo_m_conf = None, 0.0

            if a0a and a0b and abs(a0a - a0b) / max(a0a, 0.01) < 0.05:
                # Accord des deux OCR → résultat très fiable
                montant, m_score, layer = a0a, max(s0a, 0.92), "OCR.Space+Paddle-C0"
                print(f"    ✅ [C0-Accord] {a0a} DT — les deux OCR concordent ({m_score:.0%})")
            elif a0a and hash_c0a and s0a >= 0.95:
                # OCR.Space seul mais avec délimiteurs # trouvés dans le texte → fiable
                montant, m_score, layer = a0a, s0a, "OCR.Space-C0-Hash"
                print(f"    ✅ [C0-OCR.Space#] {a0a} DT — # markers détectés ({s0a:.0%})")
            else:
                # Désaccord ou absence de #...# → cascade YOLO+OCR complète
                print(f"    [C0] pas d'accord fiable → cascade YOLO+OCR...")
                cropped, bbox_m, yolo_m_conf = self.yolo_montant.crop_best(image)
                montant, m_score, layer = await asyncio.get_event_loop(
                ).run_in_executor(None, lambda: cascade_montant(cropped))

            extracted["montant_chiffres"]     = montant
            extracted["montant_chiffres_str"] = str(montant) if montant else ""

            if montant:
                print(f"    ✅ {montant} DT via {layer} ({m_score:.0%})")
            else:
                print(f"    ❌ Non détecté")
                m_score = 0.0

            # ══════════════════════════════════════════════════
            # ② MONTANT EN LETTRES
            # ══════════════════════════════════════════════════
            print("\n  ② Montant en lettres")
            lettres_ocr = None

            if self.yolo_phase3.model:
                crops = self.yolo_phase3.detect_all_fields(image)
                if "montant_lettres" in crops:
                    raw = ocr_field(crops["montant_lettres"], "montant_lettres")
                    # ✅ FIX 3 : Valider que c'est du vrai texte en lettres
                    if raw and len(raw.split()) >= 2:
                        lettres_ocr = raw
                        print(f"    ✅ OCR lettres : '{raw[:60]}'")
                    else:
                        print(f"    ⚠️  OCR lettres invalide : '{raw[:40]}'")

            if not lettres_ocr and montant:
                lettres_auto = _num2words_fr(montant)
                extracted["montant_lettres"] = lettres_auto
                extracted["lettres_source"]  = "auto_generees"
                print(f"    ⚠️  Auto-généré : '{lettres_auto[:60]}'")
                print(f"       → human_review_required = True")
            elif lettres_ocr:
                extracted["montant_lettres"] = lettres_ocr
                extracted["lettres_source"]  = "ocr"
            else:
                print(f"    ❌ Non disponible")

            # ══════════════════════════════════════════════════
            # ③ BÉNÉFICIAIRE (YOLO spécialisé en priorité)
            # ══════════════════════════════════════════════════
            print("\n  ③ Bénéficiaire")
            benef_found = False
            if self.yolo_benef.model:
                # y_range 28-55% : exclut zone tireur (0.55+) pour éviter confusion
                crop_b, bbox_b, conf_b = self.yolo_benef.crop_best(
                    image, conf=YOLO_CONF_SPEC, y_range=(0.28, 0.55))
                text = ""
                if bbox_b is not None:
                    print(f"    [YOLO-Benef] conf={conf_b:.2f} taille={crop_b.shape[1]}x{crop_b.shape[0]}")

                    # Stratégie 1 : PaddleOCR positionnel — ignore gauche (label imprimé)
                    # "À l'ordre de / لأمر" occupe ~28% gauche du crop
                    raw_pos = _paddle_ocr_from_x(crop_b, x_ratio=0.28)
                    print(f"    [YOLO-Benef] OCR positionnel (x>28%): '{raw_pos[:80]}'")
                    if raw_pos:
                        text = clean_beneficiaire(raw_pos)
                        if text:
                            print(f"    ✅ [Positionnel x>28%] '{text}'")

                    # Stratégie 2 : regex sur OCR complet
                    if not text:
                        raw_full = _paddle_ocr(crop_b)["text"] or _ocrspace(crop_b)["text"]
                        print(f"    [YOLO-Benef] OCR complet: '{raw_full[:80]}'")
                        _ORDRE_PATS = [
                            r"[àaÀA]?\s*l[''']?\s*ord(?:re\s*de?|rede?)\s+(.{3,50})",
                            r"لأمر\s+(.{3,50})",
                            r"ordrede?\s+(.{3,50})",
                        ]
                        for pat in _ORDRE_PATS:
                            m = re.search(pat, raw_full, re.IGNORECASE)
                            if m:
                                candidate = clean_beneficiaire(m.group(1).strip())
                                if candidate:
                                    text = candidate
                                    print(f"    ✅ [Regex ordre] '{text}'")
                                    break

                    # Stratégie 3 : crop physique 28% skip
                    if not text:
                        w_c = crop_b.shape[1]
                        crop_skip = crop_b[:, int(w_c * 0.28):]
                        text = ocr_field(crop_skip, "beneficiaire")
                        if text:
                            print(f"    ✅ [Skip 28%] '{text}'")
                else:
                    print(f"    [YOLO-Benef] rien détecté")

                if text:
                    extracted["beneficiaire"] = text
                    benef_found = True
                else:
                    print(f"    ⚠️  [YOLO-Benef] bénéficiaire non lisible")
            if not benef_found and self.yolo_phase3.model:
                crops = self.yolo_phase3.detect_all_fields(image)
                if "beneficiaire" in crops:
                    text = ocr_field(crops["beneficiaire"], "beneficiaire")
                    if text:
                        extracted["beneficiaire"] = text
                        benef_found = True
                        print(f"    ✅ [YOLO-Phase3] '{text}'")
                    else:
                        print(f"    ⚠️  [YOLO-Phase3] artefact rejeté")
                else:
                    print(f"    ⚠️  Zone non détectée (tous modèles)")

            # VLM fallback — crop positionnel zone bénéficiaire → Gemini/Qwen/Mistral
            if not benef_found and (GEMINI_KEY or OPENROUTER_KEY or MISTRAL_KEY):
                print(f"    [VLM-Fallback] Bénéficiaire introuvable par OCR → VLM...")
                h_img, w_img = image.shape[:2]
                # Zone "À l'ordre de" : y=38-52%, x=22-80% (BCT standard)
                crop_vlm = image[int(h_img*0.38):int(h_img*0.52),
                                 int(w_img*0.22):int(w_img*0.80)]
                if crop_vlm.size == 0:
                    crop_vlm = image
                BENEF_PROMPT = (
                    "This is a section of a Tunisian bank cheque. "
                    "What is the beneficiary name written after 'À l'ordre de'? "
                    "Reply with ONLY the name (1–5 words), nothing else. "
                    "If unreadable, reply: UNKNOWN"
                )
                for svc in ["gemini", "qwen", "mistral"]:
                    if svc == "gemini" and not GEMINI_KEY:
                        continue
                    if svc == "qwen" and not OPENROUTER_KEY:
                        continue
                    if svc == "mistral" and not MISTRAL_KEY:
                        continue
                    print(f"    [VLM-{svc.capitalize()}]...", end=" ", flush=True)
                    r_vlm = _vlm(crop_vlm, BENEF_PROMPT, svc)
                    vlm_text = r_vlm.get("text", "").strip()
                    if vlm_text and vlm_text.upper() not in ("UNKNOWN", ""):
                        candidate = clean_beneficiaire(vlm_text)
                        if candidate:
                            extracted["beneficiaire"] = candidate
                            benef_found = True
                            print(f"✅ '{candidate}'")
                            break
                        else:
                            print(f"artefact '{vlm_text[:30]}'")
                    else:
                        print(f"non lisible")

            # ══════════════════════════════════════════════════
            # ④ DATE & LIEU (YOLO spécialisé en priorité)
            # ══════════════════════════════════════════════════
            # Patterns qui indiquent qu'on a capturé la zone d'expiration (bas du chèque)
            # et non la zone manuscrite date/lieu
            _EXPIR_PATTERNS = [
                r"valeur\s*maximale", r"chequen[°o]", r"BPD",
                r"date\s+d.expir", r"تاريخ\s+انتهاء", r"#\d{3,}",
                r"صالح\s+إلى",
                r"signature[s]?\b",      # zone signature capturée par erreur
                r"[a-z]{2,}\d[a-z]{2,}", # bruit OCR cursif (ex: "sc4Jl")
                r"les\s+ch[eè]ques",     # texte imprimé du disclaimer certifié
                r"certif[ié]",           # "certifiés/certifles" — texte pre-imprimé
                r"ne\s+sont\s+pas",      # suite du disclaimer imprimé
                r"^\s*/\d{4}",           # commence par /AAAA (fragment date expiration)
            ]

            def _is_expiration_zone(text: str) -> bool:
                t = text.lower()
                return any(re.search(p, t, re.IGNORECASE) for p in _EXPIR_PATTERNS)

            print("\n  ④ Date & Lieu")
            date_found = False
            if self.yolo_datelieu.model:
                # y_range 60-90% : date/lieu en bas-droit, au-dessus du cadre expiration
                crop_dl, bbox_dl, _ = self.yolo_datelieu.crop_best(
                    image, conf=YOLO_CONF_SPEC, y_range=(0.60, 0.90))
                if bbox_dl is None:
                    # Aucune détection → ne pas OCR l'image entière
                    raw_dl = ""
                    print(f"    [YOLO-DateLieu] rien détecté → fallback positionnel")
                else:
                    raw_dl = _paddle_ocr(crop_dl)["text"] or _ocrspace(crop_dl)["text"]
                    # Rejeter si le modèle a capturé la zone d'expiration imprimée
                    if _is_expiration_zone(raw_dl):
                        raw_dl = ""
                        print(f"    ⚠️  [YOLO-DateLieu] Zone d'expiration — ignorée")

                date_val = clean_date(raw_dl)
                lieu_val = clean_lieu(raw_dl)
                if date_val:
                    extracted["date"] = date_val
                    date_found = True
                    print(f"    ✅ [YOLO-DateLieu] Date: '{date_val}'")
                if lieu_val:
                    extracted["lieu"] = lieu_val
                    print(f"    ✅ [YOLO-DateLieu] Lieu: '{lieu_val}'")
                # Combiné pour report_formatter
                parts = [p for p in [date_val, lieu_val] if p]
                if parts:
                    extracted["date_lieu"] = " — ".join(parts)
                if not date_val:
                    print(f"    ⚠️  [YOLO-DateLieu] date non parsée: '{raw_dl[:40]}'")
            if not date_found and self.yolo_phase3.model:
                crops = self.yolo_phase3.detect_all_fields(image)
                for fk in ["date_lieu", "date"]:
                    if fk in crops:
                        text = ocr_field(crops[fk], "date")
                        if text:
                            extracted["date"] = text
                            extracted["date_lieu"] = text
                            date_found = True
                            print(f"    ✅ [YOLO-Phase3] '{text}'")
                            break

            # Fallback positionnel : crop bas-droite au-dessus du cadre expiration
            if not date_found:
                print(f"    [Fallback] crop positionnel date/lieu...")
                crop_pos = _crop_positional_datelieu(image)
                raw_pos = _paddle_ocr(crop_pos)["text"] or _ocrspace(crop_pos)["text"]
                print(f"    [Fallback] OCR brut: '{raw_pos[:60]}'")
                if raw_pos and not _is_expiration_zone(raw_pos):
                    date_val_pos = clean_date(raw_pos)
                    lieu_val_pos = clean_lieu(raw_pos)
                    if date_val_pos:
                        extracted["date"] = date_val_pos
                        print(f"    ✅ [Positionnel] Date: '{date_val_pos}'")
                    if lieu_val_pos:
                        extracted["lieu"] = lieu_val_pos
                        print(f"    ✅ [Positionnel] Lieu: '{lieu_val_pos}'")
                    if date_val_pos or lieu_val_pos:
                        parts = [p for p in [date_val_pos, lieu_val_pos] if p]
                        extracted["date_lieu"] = " — ".join(parts)
                    else:
                        print(f"    ⚠️  Fallback : date non parsée")
                else:
                    print(f"    ⚠️  Fallback : zone expiration ou vide")

            # ══════════════════════════════════════════════════
            # ⑤ TIREUR (émetteur du chèque)
            # ══════════════════════════════════════════════════
            print("\n  ⑤ Tireur")
            tireur_val = None

            # Essai YOLO-Tireur spécialisé
            if self.yolo_tireur.model:
                # y_range 55-82% : commence APRÈS zone benef (0.55), avant date expiration (0.83+)
                crop_t, bbox_t, conf_t = self.yolo_tireur.crop_best(
                    image, conf=YOLO_CONF_SPEC, y_range=(0.55, 0.82))
                if bbox_t is not None:
                    print(f"    [YOLO-Tireur] détecté conf={conf_t:.2f}")
                    raw_t = _paddle_ocr(crop_t)["text"] or _ocrspace(crop_t)["text"]
                    tireur_val = clean_tireur(raw_t)
                    if tireur_val:
                        print(f"    ✅ [YOLO-Tireur] '{tireur_val}'")
                    else:
                        print(f"    ⚠️  [YOLO-Tireur] non lisible: '{raw_t[:40]}'")
                else:
                    print(f"    [YOLO-Tireur] rien détecté → fallback positionnel")
                    tireur_val = None  # reset explicite

            # Fallback positionnel — bloc central (Titulaire du compte)
            if not tireur_val:
                print(f"    [Fallback] crop positionnel tireur (bloc titulaire)...")
                crop_pos_t = _crop_positional_tireur(image)
                raw_pos_t = _paddle_ocr(crop_pos_t)["text"] or _ocrspace(crop_pos_t)["text"]
                print(f"    [Fallback] OCR brut: '{raw_pos_t[:60]}'")

                # 1. Ancrage label imprimé "Titulaire du compte / صاحب الحساب"
                _TITUL_PATS = [
                    r'titulaire\s*du\s*compte\s*/?\s*(?:صاحب\s*الحساب)?\s*[:\-]?\s*([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-Za-zÀ-ÿ\s\-\.&]{2,60})',
                    r'صاحب\s*الحساب\s*[:\-]?\s*([A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ][A-Za-zÀ-ÿ\s\-\.&]{2,60})',
                ]
                for pat in _TITUL_PATS:
                    m = re.search(pat, raw_pos_t, re.IGNORECASE)
                    if m:
                        candidate = clean_tireur(m.group(1).strip())
                        if candidate and len(candidate) >= 3:
                            tireur_val = candidate
                            print(f"    ✅ [Ancrage titulaire] '{tireur_val}'")
                            break

                # 2. Line-by-line — ignorer labels imprimés, garder le premier vrai nom
                if not tireur_val:
                    _SKIP_LABELS = re.compile(
                        r'^(?:banque|agence|compte|cl[eé]|payable|titulaire|'
                        r'صاحب|يدفع|bq\b|ag\b|\d{2,})', re.IGNORECASE)
                    for line in raw_pos_t.splitlines():
                        line = line.strip()
                        if not line or _SKIP_LABELS.match(line):
                            continue
                        candidate = clean_tireur(line)
                        if candidate and len(candidate) >= 4:
                            tireur_val = candidate
                            print(f"    ✅ [Positionnel] '{tireur_val}'")
                            break

                if not tireur_val:
                    print(f"    ⚠️  Zone tireur illisible ou vide")

            if tireur_val:
                extracted["tireur"]    = tireur_val
                extracted["titulaire"] = tireur_val

            # ══════════════════════════════════════════════════
            # ⑥ AGENCE bancaire
            # ══════════════════════════════════════════════════
            print("\n  ⑥ Agence")
            if self.yolo_agence.model:
                crop_a, bbox_a, conf_a = self.yolo_agence.crop_best(image)
                if bbox_a is not None:
                    print(f"    [YOLO-Agence] détecté conf={conf_a:.2f} taille={crop_a.shape[1]}x{crop_a.shape[0]}")
                # OCR neutre (pas de clean_beneficiaire agressif)
                raw_a = _paddle_ocr(crop_a)["text"] or _ocrspace(crop_a)["text"]
                agence_val = clean_agence(raw_a)
                if agence_val:
                    extracted["agence"] = agence_val
                    print(f"    ✅ [YOLO-Agence] '{agence_val}'")
                else:
                    print(f"    ⚠️  [YOLO-Agence] non lisible: '{raw_a[:40]}'")
            else:
                print(f"    ⚠️  YOLO-Agence absent — fallback positionnel")
                crop_pos_a = _crop_positional_agence(image)
                raw_pos_a = _paddle_ocr(crop_pos_a)["text"] or _ocrspace(crop_pos_a)["text"]
                agence_pos = clean_agence(raw_pos_a)
                if agence_pos:
                    extracted["agence"] = agence_pos
                    print(f"    ✅ [Positionnel] '{agence_pos}'")

            # ══════════════════════════════════════════════════
            # ⑦ RESCUE PAR CONTEXTE — ancrage labels BCT
            # ══════════════════════════════════════════════════
            # Champs encore manquants après les YOLO spécialisés ?
            missing = [k for k in ["montant_chiffres","beneficiaire","date","lieu","tireur","agence"]
                       if not extracted.get(k)]
            if missing:
                print(f"\n  ⑦ Context rescue ({len(missing)} champ(s) : {missing})...")
                ctx = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: _extract_by_context(image)
                )
                for key, val in ctx.items():
                    if not extracted.get(key) and val:
                        extracted[key] = val
                        if key == "montant_chiffres":
                            m_score = max(m_score, 0.80)
                        print(f"    ✅ [Context] {key}: '{val}'")
                # Mise à jour alias tireur→titulaire
                if extracted.get("tireur") and not extracted.get("titulaire"):
                    extracted["titulaire"] = extracted["tireur"]
                # Mise à jour date_lieu combiné
                parts = [p for p in [extracted.get("date"), extracted.get("lieu")] if p]
                if parts and not extracted.get("date_lieu"):
                    extracted["date_lieu"] = " — ".join(parts)

            # Fallback positionnel si context a aussi raté le montant
            if not extracted["montant_chiffres"]:
                print("    [Positionnel] Montant crop top-right...")
                crop_m_pos = _crop_positional_montant(image)
                raw_m_pos = _ocrspace(crop_m_pos)["text"] or _paddle_ocr(crop_m_pos)["text"]
                amount_pos, _ = parse_amount(raw_m_pos)
                if amount_pos and 0.1 <= amount_pos <= 500_000:
                    extracted["montant_chiffres"] = amount_pos
                    m_score = max(m_score, 0.75)
                    print(f"    ✅ [Positionnel] Montant: {amount_pos} DT")

            # Fallback positionnel bénéficiaire
            if not extracted["beneficiaire"]:
                print("    [Positionnel] Bénéficiaire crop ligne ordre...")
                crop_b_pos = _crop_positional_benef(image)
                raw_b_pos = _paddle_ocr(crop_b_pos)["text"] or _ocrspace(crop_b_pos)["text"]
                if raw_b_pos:
                    # Supprimer le label imprimé "À l'ordre de" qui peut rester
                    raw_b_pos = re.sub(r"[Àa]\s*l[''']?\s*ordre\s*de\s*[-_\.]*\s*", "", raw_b_pos,
                                       flags=re.IGNORECASE).strip()
                    candidate = clean_beneficiaire(raw_b_pos)
                    if candidate:
                        extracted["beneficiaire"] = candidate
                        print(f"    ✅ [Positionnel] Bénéficiaire: '{candidate}'")

            # ══════════════════════════════════════════════════
            # DÉCISION FINALE
            # ══════════════════════════════════════════════════
            # Champs obligatoires (score principal)
            n_obligatoires = sum(1 for v in [
                extracted["montant_chiffres"],
                extracted["montant_lettres"],
                extracted["beneficiaire"],
                extracted["date"]
            ] if v)

            # Champs supplémentaires (bonus)
            n_bonus = sum(1 for v in [
                extracted["tireur"],
                extracted["agence"],
                extracted["lieu"],
            ] if v)
            n_remplis = n_obligatoires + n_bonus

            final_score      = round(n_obligatoires / 4.0 * max(m_score, 0.5), 3)
            lettres_auto_gen = extracted["lettres_source"] == "auto_generees"
            # human_review si montant absent OU lettres non vérifiées par OCR
            # (lettres auto-générées = agent bancaire doit valider manuellement)
            human_review     = extracted["montant_chiffres"] is None or lettres_auto_gen
            cross_ok         = (montant is not None
                                and extracted["montant_lettres"] is not None)

            print(f"\n  {'─'*55}")
            print(f"  Résultat Phase 3 v4.0 :")
            print(f"    Montant chiffres : {extracted['montant_chiffres']} DT")
            print(f"    Montant lettres  : {(extracted['montant_lettres'] or '')[:50]}")
            print(f"    Source lettres   : {extracted['lettres_source']}")
            print(f"    Bénéficiaire     : {extracted['beneficiaire']}")
            print(f"    Date             : {extracted['date']}")
            print(f"    Lieu             : {extracted['lieu']}")
            print(f"    Tireur           : {extracted['tireur']}")
            print(f"    Agence           : {extracted['agence']}")
            print(f"    Score            : {final_score:.0%}")
            print(f"    Champs obligat.  : {n_obligatoires}/4  |  Bonus: {n_bonus}/3")
            print(f"    Agent vérifie    : {'⚠️  OUI' if human_review else '✅ NON'}")

            return PhaseResult(
                phase="ocr",
                score=final_score,
                passed=not human_review,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "extracted":               extracted,
                    "cross_validation_passed": cross_ok,
                    "human_review_required":   human_review,
                    "lettres_auto_generees":   lettres_auto_gen,
                    "yolo_montant": {
                        "zone_detectee": bbox_m is not None,
                        "confiance":     round(yolo_m_conf, 3),
                    },
                    "champs_obligatoires": n_obligatoires,
                    "champs_bonus":        n_bonus,
                    "champs_remplis":      n_remplis,
                    "decision": "OCR_SUCCESS" if not human_review
                    else "PENDING_MANUAL_REVIEW",
                    "score": final_score,
                }
            )

        except Exception as e:
            import traceback; traceback.print_exc()
            return self._error(str(e)[:100], t0)

    def _error(self, msg: str, t0: float) -> PhaseResult:
        return PhaseResult(
            phase="ocr", score=0.0, passed=False,
            duration_ms=int((time.time()-t0)*1000),
            details={
                "extracted":{"montant_chiffres":None,"montant_lettres":None,
                             "beneficiaire":None,"date":None},
                "cross_validation_passed":False,
                "human_review_required":True,
                "decision":"ERROR","error":msg
            }
        )


# ═══════════════════════════════════════════════════════════════
# TEST STANDALONE
# ═══════════════════════════════════════════════════════════════

async def _test():
    print("\n╔══════════════════════════════════════════════════════════╗")
    print("║  Phase 3 v3.0 — Test avec FIXES                         ║")
    print("╚══════════════════════════════════════════════════════════╝\n")
    from dotenv import load_dotenv
    load_dotenv()
    phase3 = OCRPhaseV2()
    for img_path, expected in [
        ("Chequetest/chequeN.jpg", 958.5),
        ("Chequetest/chequeR.jpg", 200.0),
        ("Chequetest/recto.jpg",   1652.824),
        ("Chequetest/ChequeT.jpg", 700.0),
    ]:
        if not Path(img_path).exists(): continue
        print(f"\n{'═'*60}")
        print(f"  {Path(img_path).name}  (attendu: {expected} DT)")
        print(f"{'═'*60}")
        with open(img_path, "rb") as f:
            result = await phase3.extract(f.read())
        m = result.details["extracted"]["montant_chiffres"]
        if m:
            err = abs(m - expected) / expected * 100
            icon = "✅" if err < 2 else "⚠️ " if err < 10 else "❌"
        else:
            err, icon = None, "❌"
        print(f"\n  {icon} Montant : {m} DT"
              + (f" (erreur: {err:.1f}%)" if err else ""))

if __name__ == "__main__":
    asyncio.run(_test())