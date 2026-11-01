"""
app/phases/phase2_compliance.py — CORRIGÉ
FIXES :
  1. validate_banque() → dictionnaire BCT (sans DB)
  2. comparer_qr_physique() → + Titulaire + CMC7
  3. _build() → compatible avec nouveau format comp
"""

import cv2, re, os, sys, time
import numpy as np
from datetime import date, datetime, timedelta

try:
    from pyzbar import pyzbar
    from pyzbar.pyzbar import ZBarSymbol
    HAS_PYZBAR = True
except ImportError:
    HAS_PYZBAR = False

try:
    from zxing import BarCodeReader
    HAS_ZXING = True
except ImportError:
    HAS_ZXING = False

try:
    from ultralytics import YOLO as _YOLO
    HAS_YOLO = True
except ImportError:
    HAS_YOLO = False

try:
    from qreader import QReader
    HAS_QREADER = True
except ImportError:
    HAS_QREADER = False

from sqlalchemy import text

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.database               import db_engine
from app.models.pipeline_models import PhaseResult
from app.phases.phase2_ocr_yolo import OCRYolo

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

JOURS_FERIES = [(1,1),(3,20),(4,9),(5,1),(7,25),(8,13),(10,15),(11,7)]

# ═══════════════════════════════════════════════════════════════════
# Dictionnaire BCT — 21 banques agréées (FIX : sans DB)
# ═══════════════════════════════════════════════════════════════════
RIB_BANK_MAP = {
    "01": "ATB (Arab Tunisian Bank)",
    "03": "BNA (Banque Nationale Agricole)",
    "04": "Attijari Bank",
    "05": "BT (Banque de Tunisie)",
    "07": "Amen Bank",
    "08": "BIAT (Banque Internationale Arabe de Tunisie)",
    "10": "STB (Société Tunisienne de Banque)",
    "11": "UBCI (Union Bancaire pour le Commerce et l'Industrie)",
    "12": "UIB (Union Internationale de Banques)",
    "14": "BH Bank",
    "16": "Citibank",
    "17": "La Poste Tunisienne",
    "20": "BTK (Banque Tuniso-Koweïtienne)",
    "21": "TSB (Tunisian Saudi Bank)",
    "23": "QNB (Qatar National Bank)",
    "24": "BTE (Banque de Tunisie et des Émirats)",
    "25": "Banque Zitouna",
    "26": "BTL (Banque Tuniso-Libyenne)",
    "28": "Bank ABC",
    "32": "Al Baraka Bank",
    "47": "Wifak Bank",
}


class TuniChequeCompliancePhase:

    DELAI_OUVRABLES   = 8
    MONTANT_MIN       = 0.1
    MONTANT_MAX       = 10_000_000
    SEUIL_NUM_CHEQUE  = 0.70
    SEUIL_RIB         = 0.80
    SEUIL_DATE        = 0.90
    SEUIL_TITULAIRE   = 0.70
    TOLERANCE_MONTANT = 1.0

    def __init__(self):
        self.db_engine = db_engine
        self.ocr_yolo  = OCRYolo()
        yolo_path = os.getenv("YOLO_MODEL_PATH", "saved_models/best.pt")
        self._yolo = _YOLO(yolo_path) if (HAS_YOLO and os.path.exists(yolo_path)) else None
        self._zxing  = BarCodeReader() if HAS_ZXING else None
        self.qreader = QReader() if HAS_QREADER else None
        logger.info("phase2_init",
                    pyzbar=HAS_PYZBAR, zxing=HAS_ZXING,
                    qreader=self.qreader is not None,
                    yolo_qr=self._yolo is not None,
                    yolo=self.ocr_yolo.yolo_disponible)

    # ── QR ────────────────────────────────────────────────────────────────

    def read_qr(self, image_bytes: bytes) -> dict | None:
        try:
            arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None: return None
            h, w = img.shape[:2]

            # QReader AI (deep learning)
            if self.qreader:
                try:
                    decoded = self.qreader.detect_and_decode(image=img)
                    if decoded:
                        for d in decoded:
                            if d and "pecc.tn" in d.lower():
                                logger.info("qreader_success", debut=d[:50])
                                r = self._parse_pecc(d)
                                r["raw"] = d
                                logger.info("qr_raw_found", debut=d[:50])
                                return r
                except Exception as e:
                    logger.warning("qreader_error", error=str(e))

            # Fallback pyzbar / cv2
            return self._decode_raw_qr(img, h, w)

        except Exception as e:
            logger.warning("read_qr_error", error=str(e))
            return None

    def _decode_raw_qr(self, img, h, w):
        gray    = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe   = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced= clahe.apply(gray)
        det     = cv2.QRCodeDetector()
        passes  = [
            img,
            cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR),
            cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR),
            cv2.resize(img, (w*2, h*2), interpolation=cv2.INTER_CUBIC),
            cv2.resize(img, (w*3, h*3), interpolation=cv2.INTER_CUBIC),
        ]
        for p in passes:
            try:
                data, pts, _ = det.detectAndDecode(p)
                if pts is not None and data and "pecc.tn" in data.lower():
                    r = self._parse_pecc(data); r["raw"] = data
                    return r
            except Exception: continue

        if HAS_PYZBAR:
            for scale in [1, 2, 3]:
                img_s = cv2.resize(img, (w*scale, h*scale))
                for sym in pyzbar.decode(img_s, symbols=[ZBarSymbol.QRCODE]):
                    data = sym.data.decode("utf-8", errors="ignore")
                    if "pecc.tn" in data.lower():
                        r = self._parse_pecc(data); r["raw"] = data
                        return r
        return None

    def _parse_pecc(self, raw: str) -> dict:
        r = {"is_pecc": False, "format_detecte": "inconnu", "raw": raw}
        try:
            clean = raw.strip()
            if clean.startswith("https://"): clean = clean[8:]
            if clean.startswith("http://"):  clean = clean[7:]
            p = clean.split("/")
            if len(p) < 2 or "pecc.tn" not in p[0].lower(): return r
            r.update({
                "is_pecc":      True,
                "format_detecte": "pecc_tn",
                "domaine":      p[0],
                "type":         p[1] if len(p)>1 else None,
                "numero_cheque":p[2] if len(p)>2 else None,
                "rib":          p[3] if len(p)>3 else None,
                "indicateur":   p[4] if len(p)>4 else None,
                "beneficiaire": p[5] if len(p)>5 else None,
            })
            if len(p) > 6:
                raw_m = re.sub(r'\D', '', p[6])
                if raw_m: r["montant"] = float(int(raw_m)) / 1000.0
                r["montant_raw"] = p[6]
            if len(p) > 7:
                raw_d = p[7].strip()
                if len(raw_d) == 8 and raw_d.isdigit():
                    r["date_emission"] = "{}/{}/{}".format(raw_d[0:2], raw_d[2:4], raw_d[4:8])
                else:
                    r["date_emission"] = raw_d
            if r.get("rib") and len(r["rib"]) >= 2:
                r["code_banque"] = r["rib"][:2]
                # Enrichir avec nom de la banque
                r["nom_banque"] = RIB_BANK_MAP.get(r["code_banque"], "Banque inconnue")
        except Exception as e:
            logger.warning("pecc_parse_erreur", error=str(e))
        return r

    # ── Validations ───────────────────────────────────────────────────────

    def _est_ouvrable(self, d: date) -> bool:
        if d.weekday() in (5, 6): return False
        for m, j in JOURS_FERIES:
            if d.month == m and d.day == j: return False
        return True

    def _ajouter_ouvrables(self, debut: date, n: int) -> date:
        c, courant = 0, debut
        while c < n:
            courant += timedelta(days=1)
            if self._est_ouvrable(courant): c += 1
        return courant

    def validate_date(self, ds: str) -> dict:
        if not ds: return {"ok": False, "reason": "date_absente"}
        de = None
        for fmt in ["%d/%m/%Y", "%d%m%Y", "%Y-%m-%d", "%d-%m-%Y"]:
            try: de = datetime.strptime(str(ds).strip(), fmt).date(); break
            except ValueError: continue
        if de is None: return {"ok": False, "reason": "format_invalide"}
        today = date.today()
        if de.year < 2025: return {"ok": False, "reason": "avant_2025"}
        if de >= today:
            return {"ok": True, "reason": "valide",
                    "date_expiration": str(de),
                    "jours_restants":  (de - today).days,
                    "date_limite":     str(de)}
        return {"ok": False, "reason": "delai_depasse",
                "date_expiration": str(de), "date_limite": str(de)}

    def validate_rib(self, rib: str) -> dict:
        rib = re.sub(r"\s", "", rib or "")
        if not re.match(r"^\d{20}$", rib):
            return {"ok": False, "reason": "longueur_{}".format(len(rib))}
        try:
            cc = 97 - int(rib[:18]) * 100 % 97
            if cc != int(rib[18:]):
                return {"ok": False, "reason": "luhn_invalide"}
        except Exception as e:
            return {"ok": False, "reason": str(e)}
        return {"ok": True, "code_banque": rib[:2]}

    def validate_montant(self, m) -> dict:
        if m is None: return {"ok": False, "reason": "absent"}
        try: v = float(m)
        except Exception: return {"ok": False, "reason": "non_numerique"}
        if v < self.MONTANT_MIN: return {"ok": False, "reason": "sous_minimum"}
        if v > self.MONTANT_MAX: return {"ok": False, "reason": "depasse_maximum"}
        return {"ok": True, "valeur_dt": round(v, 3)}

    # ═══════════════════════════════════════════════════════════════════════
    # FIX 1 — validate_banque : dictionnaire BCT (SANS DB)
    # ═══════════════════════════════════════════════════════════════════════
    def validate_banque(self, code: str) -> dict:
        """
        Validation banque via dictionnaire RIB BCT (sans requête DB).
        Les 2 premiers chiffres du RIB = code banque BCT Tunisie.
        """
        if not code:
            return {"ok": False, "reason": "code_absent"}
        code = str(code).strip().zfill(2)[:2]
        nom = RIB_BANK_MAP.get(code)
        if nom:
            logger.info("banque_validee", code=code, nom=nom)
            return {"ok": True, "code": code, "nom_banque": nom}
        else:
            logger.warning("banque_inconnue", code=code)
            return {"ok": False, "reason": "code_inconnu:{}".format(code)}

    # ── OCR physique ──────────────────────────────────────────────────────

    def extraire_ocr(self, image_bytes: bytes) -> dict:
        import base64, requests as _req

        result = self.ocr_yolo.extraire(image_bytes)
        champs_extraits = sum(1 for k in ["numero_cheque", "rib", "date", "montant"] if result.get(k))

        if champs_extraits >= 4:
            result["source_ocr"] = "yolo"
            logger.info("ocr_yolo_done", champs="{}/4".format(champs_extraits),
                        date=result.get("date"), montant=result.get("montant"),
                        num=result.get("numero_cheque"))
            return result

        # Fallback Mistral si champs manquants
        champs_manquants = 4 - champs_extraits
        logger.info("fallback_yolo_phase3_active", champs_manquants=champs_manquants)

        try:
            arr = np.frombuffer(image_bytes, np.uint8)
            img_np = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img_np is None: return result

            # YOLO Phase 3 fallback
            yolo_p3_path = os.getenv("YOLO_OCR_PATH", "saved_models/yolo_ocr/best_v24.pt")
            if HAS_YOLO and os.path.exists(yolo_p3_path):
                yolo3 = _YOLO(yolo_p3_path)
                res3  = yolo3(img_np, verbose=False)
                for r in res3:
                    for box in r.boxes:
                        name = r.names[int(box.cls)]
                        x1,y1,x2,y2 = map(int, box.xyxy[0])
                        crop = img_np[y1:y2, x1:x2]
                        if crop.size == 0: continue
                        logger.debug("yolo_phase3_zone", nom=name)

            # Niveau 2 : Mistral Vision
            logger.info("extraire_ocr_niveau2_mistral", champs_niveau1=champs_extraits)
            _, buf = cv2.imencode(".jpg", img_np)
            b64    = base64.b64encode(buf.tobytes()).decode()
            api_key= os.getenv("MISTRAL_API_KEY", "")
            if not api_key: return result

            prompt = (
                "Tu es un OCR spécialisé chèques bancaires tunisiens. "
                "Extrais en JSON strict : numero_cheque, rib (20 chiffres), "
                "date (JJ/MM/AAAA), montant (nombre). "
                "Réponds UNIQUEMENT avec le JSON, sans texte autour."
            )
            resp = _req.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": "Bearer " + api_key,
                         "Content-Type": "application/json"},
                json={"model": "pixtral-large-latest", "max_tokens": 300,
                      "messages": [{"role": "user", "content": [
                          {"type": "text",      "text": prompt},
                          {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}}
                      ]}]},
                timeout=30
            )
            if resp.status_code == 200:
                txt = resp.json()["choices"][0]["message"]["content"].strip()
                txt = txt.replace("```json","").replace("```","").strip()
                import json as _json
                parsed = _json.loads(txt)
                for k in ["numero_cheque", "rib", "date", "montant"]:
                    if not result.get(k) and parsed.get(k):
                        result[k] = parsed[k]
                        logger.info("ocr_mistral_complete", champ=k, val=str(parsed[k])[:30])
                champs_ok = sum(1 for k in ["numero_cheque","rib","date","montant"] if result.get(k))
                logger.info("extraire_ocr_niveau2_ok", champs=champs_ok)
        except Exception as e:
            logger.warning("ocr_niveau2_erreur", error=str(e))

        result["source_ocr"] = "yolo+mistral"
        return result

    # ═══════════════════════════════════════════════════════════════════════
    # FIX 2+3 — comparer_qr_physique : + CMC7 + Titulaire
    # ═══════════════════════════════════════════════════════════════════════
    def comparer_qr_physique(self, qr: dict, ocr: dict) -> dict:
        """
        Compare 5 champs QR vs OCR physique :
          N° cheque  sim >= 70%
          N° Compte  sim >= 80%
          Date       sim >= 90%
          Plafond    diff < 1 DT
          Titulaire  sim >= 70%  (PENDING_YOLO si OCR absent)

        + Compose CMC7 = numero_cheque + "1" + RIB (norme BCT)
        """
        violations = []; warnings = []; comps = {}

        def _champ(key, label, qr_val, ocr_val, mode):
            if qr_val and ocr_val:
                if mode == "sim":
                    seuil = {"numero_cheque": self.SEUIL_NUM_CHEQUE,
                             "rib":           self.SEUIL_RIB,
                             "date":          self.SEUIL_DATE,
                             "titulaire":     self.SEUIL_TITULAIRE}[key]
                    s  = self._sim(str(qr_val), str(ocr_val))
                    ok = s >= seuil
                    comps[key] = {"champ": label, "qr": str(qr_val),
                                  "ocr": str(ocr_val), "status": "OK" if ok else "FAIL",
                                  "detail": "sim={}%".format(int(s * 100))}
                    if not ok:
                        violations.append("{}_incoherent QR={} OCR={}".format(key, qr_val, ocr_val))
                else:  # montant
                    qm = self._norm_montant(qr_val)
                    om = self._norm_montant(ocr_val)
                    if qm and om:
                        d  = abs(qm - om)
                        ok = d < self.TOLERANCE_MONTANT
                        comps[key] = {"champ": label, "qr": str(qm), "ocr": str(om),
                                      "status": "OK" if ok else "FAIL",
                                      "detail": "diff={} DT".format(round(d, 1))}
                        if not ok:
                            violations.append("plafond_incoherent QR={} OCR={}".format(qm, om))
            elif qr_val:
                comps[key] = {"champ": label, "qr": str(qr_val),
                              "ocr": None, "status": "WARN_OCR_MANQUANT"}
                warnings.append("{}: ocr_non_extrait".format(label))
            else:
                comps[key] = {"champ": label, "status": "NON_VERIFIE"}

        # 4 comparaisons originales
        _champ("numero_cheque", "N° cheque",
               qr.get("numero_cheque"), ocr.get("numero_cheque"), "sim")
        _champ("rib", "N° Compte (RIB)",
               re.sub(r'\s', '', qr.get("rib", "") or ""),
               re.sub(r'\s', '', ocr.get("rib", "") or ""), "sim")
        _champ("date", "Date de validite",
               self._norm_date(qr.get("date_emission")),
               self._norm_date(ocr.get("date")), "sim")
        _champ("montant", "Plafond (montant maximum)",
               qr.get("montant"), ocr.get("montant"), "montant")

        # Titulaire — Phase 2 OCR (tireur) ou Phase 3 (titulaire) via main.py
        qr_benef  = (qr.get("beneficiaire") or "").strip()
        ocr_titul = (ocr.get("titulaire") or ocr.get("titulaire_nom")
                     or ocr.get("tireur") or "").strip()
        if qr_benef and ocr_titul:
            _champ("titulaire", "Titulaire / Bénéficiaire",
                   qr_benef.upper(), ocr_titul.upper(), "sim")

        # FIX 2 — CMC7 depuis QR (norme BCT)
        cmc7 = None
        num  = re.sub(r'\s', '', qr.get("numero_cheque", "") or "")
        rib  = re.sub(r'\s', '', qr.get("rib", "") or "")
        if num and rib:
            cmc7 = "{}1{}".format(num, rib)
            logger.info("cmc7_compose", num=num, cmc7=cmc7[:15]+"...")

        # Format tableau pour le rapport
        tableau = [
            {"champ": v.get("champ", k), "qr": v.get("qr"),
             "ocr": v.get("ocr"), "status": v.get("status"),
             "detail": v.get("detail", "")}
            for k, v in comps.items()
        ]

        return {
            "tableau":    tableau,
            "comparaisons": comps,   # conservé pour _build()
            "resume": {
                "champs_ok":      sum(1 for c in comps.values() if c.get("status") == "OK"),
                "champs_fail":    sum(1 for c in comps.values() if c.get("status") == "FAIL"),
                "champs_absent":  sum(1 for c in comps.values() if "MANQUANT" in c.get("status","")),
                "champs_pending": sum(1 for c in comps.values() if "PENDING" in c.get("status","")),
                "source_ocr":     ocr.get("source_ocr", "inconnu"),
            },
            "passed":     len(violations) == 0,
            "violations": violations,
            "warnings":   warnings,
            "cmc7":       cmc7,
        }

    # ── Helpers ───────────────────────────────────────────────────────────

    def _sim(self, a: str, b: str) -> float:
        a, b = a.upper().strip(), b.upper().strip()
        if not a or not b: return 0.0
        if a == b: return 1.0
        la, lb = len(a), len(b)
        mat = [[0]*(lb+1) for _ in range(la+1)]
        for i in range(la+1): mat[i][0] = i
        for j in range(lb+1): mat[0][j] = j
        for i in range(1,la+1):
            for j in range(1,lb+1):
                cost = 0 if a[i-1]==b[j-1] else 1
                mat[i][j] = min(mat[i-1][j]+1, mat[i][j-1]+1, mat[i-1][j-1]+cost)
        dist = mat[la][lb]
        return round(1.0 - dist/max(la,lb), 4)

    def _norm_date(self, d) -> str | None:
        if not d: return None
        d = str(d).strip()
        for fmt in ["%d/%m/%Y", "%d%m%Y", "%Y-%m-%d", "%d-%m-%Y"]:
            try:
                return datetime.strptime(d, fmt).strftime("%d/%m/%Y")
            except ValueError: continue
        return str(d).strip()

    def _norm_montant(self, v) -> float | None:
        if v is None: return None
        try: return round(float(str(v).replace(',', '.')), 2)
        except Exception: return None

    # ── Point d'entrée ────────────────────────────────────────────────────

    async def analyze(self, recto_bytes: bytes, cheque_id: str) -> PhaseResult:
        t0   = time.time()
        viol = []; warn = []; checks = {}

        qr = self.read_qr(recto_bytes)
        checks["qr_lisible"] = (qr is not None and qr.get("is_pecc", False))

        if qr is None:
            warn.append("qr_illisible")
            return self._build("PENDING_REVIEW_QR_ILLISIBLE",
                               viol, warn, {"qr_lisible": False},
                               None, None, None, t0, 0.0)

        if not qr.get("is_pecc", False):
            viol.append("qr_domaine_non_pecc:{}".format(qr.get("raw", "")[:30]))
            return self._build("REJECTED_QR_NON_PECC",
                               viol, warn, {"qr_lisible": False},
                               qr, None, None, t0, 0.0)

        rib_r = self.validate_rib(qr.get("rib", "") or "")
        checks["rib_valide"] = rib_r["ok"]
        if not rib_r["ok"]: viol.append("rib:{}".format(rib_r["reason"]))

        bq_r = self.validate_banque(qr.get("code_banque", "") or "")
        checks["banque_valide"] = bq_r["ok"]
        if not bq_r["ok"]: viol.append("banque:{}".format(bq_r.get("reason","")))

        date_r = self.validate_date(qr.get("date_emission", "") or "")
        checks["date_valide"] = date_r["ok"]
        if not date_r["ok"]:
            viol.append("date:{}".format(date_r["reason"]))
        elif date_r.get("jours_restants", 8) <= 2:
            warn.append("{}_jours_ouvrables_restants".format(date_r["jours_restants"]))

        mont_r = self.validate_montant(qr.get("montant"))
        checks["montant_valide"] = mont_r["ok"]
        if not mont_r["ok"]: viol.append("montant:{}".format(mont_r["reason"]))

        checks["numero_present"] = bool(qr.get("numero_cheque"))

        ocr_data = self.extraire_ocr(recto_bytes)

        comp = self.comparer_qr_physique(qr, ocr_data)
        checks["qr_vs_physique_ok"] = comp["passed"]
        for v in comp["violations"]: viol.append("comparaison_{}".format(v))
        warn.extend(comp["warnings"])

        n_ok  = sum(1 for v in checks.values() if v)
        score = round(n_ok / len(checks), 4) if checks else 0.0

        if viol:
            v = " ".join(viol)
            if "domaine_non_pecc"  in v: dec = "REJECTED_QR_NON_PECC"
            elif "rib:"            in v: dec = "REJECTED_RIB_INVALIDE"
            elif "delai"           in v: dec = "REJECTED_CHEQUE_PERIME"
            elif "avant_2025"      in v: dec = "REJECTED_CHEQUE_AVANT_2025"
            elif "banque:"         in v: dec = "REJECTED_BANQUE_INVALIDE"
            elif "montant:"        in v: dec = "REJECTED_MONTANT_INVALIDE"
            elif "incoherent"      in v: dec = "REJECTED_FALSIFICATION"
            else:                        dec = "REJECTED_COMPLIANCE"
        else:
            dec = "COMPLIANCE_OK"

        logger.info("phase2_done", cheque_id=cheque_id, decision=dec,
                    ocr_source=ocr_data.get("source_ocr"), score=score)
        logger.info("phase2_done", ms=int((time.time()-t0)*1000),
                    passed=len(viol)==0, score=round(score,3))

        return self._build(dec, viol, warn, checks, qr, ocr_data, comp, t0, score, date_r)

    def _build(self, dec, viol, warn, checks, qr, ocr, comp,
               t0, score, date_r=None) -> PhaseResult:
        dur = int((time.time() - t0) * 1000)

        # Tableau de comparaison (compatible nouveau format avec comp["tableau"])
        tableau = []
        if comp:
            if "tableau" in comp:
                tableau = comp["tableau"]
            elif "comparaisons" in comp:
                for k, c in comp["comparaisons"].items():
                    tableau.append({
                        "champ":  c.get("champ", k),
                        "qr":     str(c.get("qr") or "—"),
                        "ocr":    str(c.get("ocr") or "—"),
                        "status": c.get("status", "—"),
                        "detail": c.get("detail", ""),
                    })

        return PhaseResult(
            phase       = "compliance",
            score       = score,
            passed      = len(viol) == 0,
            duration_ms = dur,
            details     = {
                "decision":   dec,
                "checks":     checks,
                "violations": viol,
                "warnings":   warn,
                "qr_data":    qr,
                "ocr_data": {
                    "numero_cheque": ocr.get("numero_cheque") if ocr else None,
                    "rib":           ocr.get("rib")           if ocr else None,
                    "date":          ocr.get("date")          if ocr else None,
                    "montant":       ocr.get("montant")       if ocr else None,
                    "confiance_ocr": ocr.get("confiance")     if ocr else None,
                    "source_ocr":    ocr.get("source_ocr")    if ocr else None,
                } if ocr else None,
                "comparaison_qr_vs_physique": {
                    "tableau":    tableau,
                    "resume":     comp["resume"]     if comp else {},
                    "passed":     comp["passed"]     if comp else False,
                    "violations": comp["violations"] if comp else [],
                    "warnings":   comp["warnings"]   if comp else [],
                    "cmc7":       comp.get("cmc7")   if comp else None,
                } if comp else None,
                "delai_info": date_r,
                "note": "Phase 2 : QR pecc.tn + BCT + comparaison N° cheque / RIB / Date / Plafond / Titulaire",
            })