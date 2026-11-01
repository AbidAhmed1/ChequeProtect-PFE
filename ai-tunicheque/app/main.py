"""
app/main.py — TuniCheque Pipeline 4 phases — Version FINALE v2.2

CHANGEMENTS v2.2 :
  - Phase 3 : Cascade OCR (YOLO + OCR.Space + PaddleOCR + VLMs)
  - Health endpoint mis à jour avec statut OCR.Space
  - Logs enrichis avec détails couches cascade
"""

import os, sys

# ═══ DOIT ÊTRE EN TOUT PREMIER — avant tout import ═════════════
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"] = "python"
os.environ["FLAGS_use_mkldnn"]                        = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"]   = "True"
os.environ["GLOG_minloglevel"]                        = "3"
os.environ["FLAGS_call_stack_level"]                  = "0"
os.environ["TF_CPP_MIN_LOG_LEVEL"]                    = "3"

import asyncio, json, math, time, warnings
from pathlib import Path

import numpy as np
warnings.filterwarnings("ignore")

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
import uvicorn


_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

load_dotenv()

from app.database              import db_engine, test_connexion
from app.phases.phase1_identification  import ChequeIdentificationPhase, ImageSource
from app.phases.phase2_compliance      import TuniChequeCompliancePhase
from app.phases.Phase3_ocr_extraction_v2 import OCRPhaseV2   # ← Cascade v2.2
from app.phases.Phase4_signature_verification import SiameseSignaturePhase
from app.models.pipeline_models        import PipelineResult, PhaseResult

import re as _re

RIB_BANK_MAP = {
    "01": "ATB (Arab Tunisian Bank)",        "03": "BNA (Banque Nationale Agricole)",
    "04": "Attijari Bank",                   "05": "BT (Banque de Tunisie)",
    "07": "Amen Bank",                       "08": "BIAT (Banque Internationale Arabe de Tunisie)",
    "10": "STB (Société Tunisienne de Banque)", "11": "UBCI",
    "12": "UIB (Union Internationale de Banques)", "14": "BH Bank",
    "16": "Citibank",                        "17": "La Poste Tunisienne",
    "20": "BTK (Banque Tuniso-Koweïtienne)", "21": "TSB (Tunisian Saudi Bank)",
    "23": "QNB (Qatar National Bank)",       "24": "BTE (Banque de Tunisie et des Émirats)",
    "25": "Banque Zitouna",                  "26": "BTL (Banque Tuniso-Libyenne)",
    "28": "Bank ABC",                        "32": "Al Baraka Bank",
    "47": "Wifak Bank",
}
from app.utils.report_formatter        import format_rapport

from app.face_kyc import router as face_kyc_router

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    class _L:
        def __init__(self):
            logging.basicConfig(level=logging.INFO,
                                format="%(asctime)s [%(levelname)s] %(message)s")
            self._l = logging.getLogger("tunicheque")
        def _f(self, m, kw):
            e = " | ".join("{}={}".format(k,v) for k,v in kw.items())
            return "{} | {}".format(m, e) if e else m
        def info(self,m,**kw):    self._l.info(self._f(m,kw))
        def warning(self,m,**kw): self._l.warning(self._f(m,kw))
        def error(self,m,**kw):   self._l.error(self._f(m,kw))
        def debug(self,m,**kw):   self._l.debug(self._f(m,kw))
    logger = _L()


def _sanitize(obj):
    if isinstance(obj, dict):        return {k:_sanitize(v) for k,v in obj.items()}
    if isinstance(obj,(list,tuple)): return [_sanitize(v) for v in obj]
    if isinstance(obj,(np.float32,np.float64,np.floating)):
        v=float(obj); return None if(math.isnan(v) or math.isinf(v)) else round(v,6)
    if isinstance(obj,(np.int32,np.int64,np.integer)): return int(obj)
    if isinstance(obj,np.bool_):   return bool(obj)
    if isinstance(obj,np.ndarray): return [_sanitize(v) for v in obj.tolist()]
    if isinstance(obj,float):      return None if(math.isnan(obj) or math.isinf(obj)) else obj
    return obj


def _err(nom, e, ms):
    logger.error("phase_erreur", phase=nom, error=str(e)[:100])
    return PhaseResult(phase=nom, score=0.0, passed=False, duration_ms=ms,
                       details={"error":str(e)[:100], "decision":"ERROR"})


# ── Application ──────────────────────────────────────────────────
app = FastAPI(
    title="TuniCheque AI — Pipeline 4 phases + KYC",
    version="2.2.0",
    description="Pipeline OCR cascade + Reconnaissance Faciale (KYC)"
)

app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

# ── ENREGISTREMENT DES ENDPOINTS KYC ─────────────────────────────
app.include_router(face_kyc_router)

SPECIMENS_DIR = Path(os.getenv("SPECIMENS_DIR", "./specimens"))


# ══════════════════════════════════════════════════════════════════
#  STARTUP — Initialisation UNIQUE des 4 phases
# ══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def on_startup():
    logger.info("service_starting", version="2.2.0", port=8083)
    SPECIMENS_DIR.mkdir(parents=True, exist_ok=True)

    print("\n" + "═"*60)
    print("  TuniCheque Pipeline v2.2 — Initialisation")
    print("═"*60)

    # Phase 1
    try:
        app.state.phase1 = ChequeIdentificationPhase()
        logger.info("phase1_ready")
        print("  ✅ Phase 1 : Identification")
    except Exception as e:
        logger.error("phase1_erreur", error=str(e)[:80])
        app.state.phase1 = None
        print(f"  ❌ Phase 1 : {str(e)[:60]}")

    # Phase 2
    try:
        app.state.phase2 = TuniChequeCompliancePhase()
        logger.info("phase2_ready")
        print("  ✅ Phase 2 : Compliance QR")
    except Exception as e:
        logger.error("phase2_erreur", error=str(e)[:80])
        app.state.phase2 = None
        print(f"  ❌ Phase 2 : {str(e)[:60]}")

    # Phase 3 — Cascade OCR
    try:
        app.state.phase3 = OCRPhaseV2()
        p3 = app.state.phase3

        logger.info("phase3_ready",
                    cascade  = True,
                    ocrspace = True,
                    paddle   = getattr(p3, "use_paddle",  False),
                    mistral  = getattr(p3, "use_mistral", False),
                    trocr    = getattr(p3, "use_trocr",   False),
                    qwen     = bool(os.getenv("OPENROUTER_API_KEY")),
                    gemini   = bool(os.getenv("GEMINI_API_KEY")),
                    claude   = bool(os.getenv("ANTHROPIC_API_KEY")),
                    )
        print("  ✅ Phase 3 : OCR Cascade")
        print(f"     C1 OCR.Space  : ✅")
        print(f"     C2 PaddleOCR  : {'✅' if getattr(p3,'use_paddle',False) else '⚠️  non disponible'}")
        print(f"     C3 Qwen-72B   : {'✅' if os.getenv('OPENROUTER_API_KEY') else '⚠️  clé manquante'}")
        print(f"     C4 Gemini     : {'✅' if os.getenv('GEMINI_API_KEY') else '⚠️  clé manquante'}")
        print(f"     C5 Mistral    : {'✅' if os.getenv('MISTRAL_API_KEY') else '⚠️  clé manquante'}")

    except Exception as e:
        logger.error("phase3_erreur", error=str(e)[:80])
        app.state.phase3 = None
        print(f"  ❌ Phase 3 : {str(e)[:60]}")

    # Phase 4
    try:
        app.state.phase4 = SiameseSignaturePhase()
        logger.info("phase4_ready")
        print("  ✅ Phase 4 : Signature Siamoise")
    except Exception as e:
        logger.error("phase4_erreur", error=str(e)[:80])
        app.state.phase4 = None
        print(f"  ❌ Phase 4 : {str(e)[:60]}")

    print("  ✅ Module KYC (OCR CIN & Face Compare) prêt")

    app.state.db_ok = test_connexion()

    print("\n" + "═"*60)
    print(f"  DB      : {'✅ OK' if app.state.db_ok else '❌ ERREUR'}")
    print(f"  Phases  : "
          f"P1={'✅' if app.state.phase1 else '❌'} "
          f"P2={'✅' if app.state.phase2 else '❌'} "
          f"P3={'✅' if app.state.phase3 else '❌'} "
          f"P4={'✅' if app.state.phase4 else '❌'}")
    print("  Service prêt sur : http://0.0.0.0:8083")
    print("═"*60 + "\n")


# ── Décision finale ──────────────────────────────────────────────
def _decide(result):
    """
    Règles de décision (priorité décroissante) :
      P1 : Rejets critiques (qualité, faux, imprimé)
      P2 : Rejets conformité QR
      P4 : Signature ne correspond pas
      QR : illisible → agent
      P3 : OCR insuffisant → saisie manuelle
      Sinon : APPROVED
    """
    p1 = result.phases.get("identification")
    p2 = result.phases.get("compliance")
    p3 = result.phases.get("ocr")
    p4 = result.phases.get("signature")

    # Priorité 1 : Rejets Phase 1
    if p1:
        REJETS_P1 = {
            "REJECTED_QUALITY": "REJECTED_IMAGE_QUALITY",
            "REJECTED_PRINTED": "REJECTED_PRINTED_CHEQUE",
            "REJECTED_FAKE":    "REJECTED_FAKE_DOCUMENT",
            "REJECTED_NO_QR":   "REJECTED_NO_TUNICHEQUE_QR",
        }
        d = p1.details.get("decision", "")
        if d in REJETS_P1:
            return REJETS_P1[d]

    # Priorité 2 : Rejets Phase 2
    if p2 and not p2.passed:
        REJETS_P2 = {
            "REJECTED_NUMERO_INCOHERENT":  "REJECTED_NUMERO_INCOHERENT",
            "REJECTED_MONTANT_FALSIFIE":   "REJECTED_MONTANT_FALSIFIE",
            "REJECTED_BANQUE_INCOHERENTE": "REJECTED_BANQUE_INCOHERENTE",
            "REJECTED_RIB_INVALIDE":       "REJECTED_RIB_INVALIDE",
            "REJECTED_CHEQUE_PERIME":      "REJECTED_CHEQUE_PERIME",
        }
        d = p2.details.get("decision", "")
        return REJETS_P2.get(d, "REJECTED_COMPLIANCE")

    # Priorité 3 : Signature
    if p4 and not getattr(p4, "passed", True):
        return "REJECTED_SIGNATURE_MISMATCH"

    # Priorité 4 : QR illisible
    if p2 and p2.details.get("decision") in (
            "PENDING_REVIEW_QR_ILLISIBLE", "PENDING_REVIEW_QR_ABSENT"):
        return "PENDING_REVIEW_QR"

    # Phase 1 PENDING_REVIEW + Phase 2 valide → continuer
    if p1 and p1.details.get("decision") == "PENDING_REVIEW":
        if p2 is None or not p2.passed:
            return "PENDING_REVIEW_AGENT"
        logger.info("p1_pending_bypasse_par_p2_ok")

    # Priorité 5 : OCR insuffisant → saisie manuelle
    if p3 and (
            p3.details.get("human_review_required") or
            not p3.details.get("cross_validation_passed", True)
    ):
        return "PENDING_MANUAL_REVIEW"

    return "APPROVED"


# ── Pipeline principal ────────────────────────────────────────────
@app.post("/api/ai/pipeline")
async def run_pipeline(
        recto:     UploadFile        = File(...),
        verso:     UploadFile | None = File(None),
        cheque_id: str               = Form(...),
        source:    str               = Form(default="mobile"),
):
    t0 = time.time()
    img_source  = ImageSource.SCANNER if source == "scanner" else ImageSource.MOBILE
    recto_bytes = await recto.read()
    verso_bytes = await verso.read() if verso is not None else b""
    result      = PipelineResult(cheque_id=cheque_id)

    logger.info("pipeline_start", cheque_id=cheque_id,
                recto_kb=len(recto_bytes)//1024)

    # ── Phase 1 ──────────────────────────────────────────────────
    t1 = time.time()
    try:
        p1 = await app.state.phase1.analyze(
            recto_bytes=recto_bytes, verso_bytes=verso_bytes,
            cheque_id=cheque_id, source=img_source)
    except Exception as e:
        p1 = _err("identification", e, int((time.time()-t1)*1000))
    p1.duration_ms = int((time.time()-t1)*1000)
    result.phases["identification"] = p1
    logger.info("phase1_done", decision=p1.details.get("decision"),
                score=round(p1.score, 3), ms=p1.duration_ms)

    # Arrêt si rejet critique Phase 1
    if p1.details.get("decision") in {
        "REJECTED_QUALITY", "REJECTED_PRINTED", "REJECTED_FAKE"}:
        result.final_decision = _decide(result)
        result.total_time_ms  = int((time.time()-t0)*1000)
        logger.info("pipeline_arret_p1", decision=result.final_decision)
        _persister(cheque_id, result)
        return JSONResponse(content=_sanitize(result.to_dict()))

    # ── Phase 2 + Phase 3 EN PARALLÈLE ───────────────────────────
    async def _p2():
        t = time.time()
        try:
            p = await app.state.phase2.analyze(
                recto_bytes=recto_bytes, cheque_id=cheque_id)
        except Exception as e:
            p = _err("compliance", e, int((time.time()-t)*1000))
        p.duration_ms = int((time.time()-t)*1000)
        logger.info("phase2_done", passed=p.passed,
                    score=round(p.score, 3), ms=p.duration_ms)
        return p

    async def _p3():
        t = time.time()
        try:
            # Phase 3 Cascade : YOLO + OCR.Space + PaddleOCR + VLMs
            p = await app.state.phase3.extract(recto_bytes)
        except Exception as e:
            p = _err("ocr", e, int((time.time()-t)*1000))
        p.duration_ms = int((time.time()-t)*1000)

        # Log détails cascade
        couches = p.details.get("couches", {})
        montant = p.details.get("extracted", {}).get("montant_chiffres")
        logger.info("phase3_done",
                    montant      = montant,
                    score        = round(p.score, 3),
                    n_couches    = len(couches),
                    human_review = p.details.get("human_review_required"),
                    ms           = p.duration_ms)
        return p

    p2, p3 = await asyncio.gather(_p2(), _p3())

    # ═══════════════════════════════════════════════════════════════
    # QR SYNC — Cohérence Phase 1 / Phase 2
    #
    # Phase 1 objectif : détecter si c'est un VRAI NOUVEAU chèque
    #   tunisien (post-2025 = QR pecc.tn obligatoire BCT)
    #   → cv2.QRCodeDetector peut rater le QR
    #   → Décision incorrecte : PENDING_REVIEW alors que c'est valide
    #
    # Phase 2 objectif : valider le contenu du QR pecc.tn
    #   → QReader AI (deep learning) trouve le QR que cv2 a raté
    #
    # Correction : si Phase 2 confirme QR pecc.tn valide →
    #   mettre à jour la DÉCISION Phase 1 :
    #   PENDING_REVIEW → VALID_CHEQUE (c'est bien un nouveau chèque)
    # ═══════════════════════════════════════════════════════════════
    try:
        p1_details  = p1.details or {}
        p1_decision = p1_details.get("decision", "")
        p2_qr_data  = (p2.details or {}).get("qr_data", {}) or {}
        p2_qr_valide = p2_qr_data.get("is_pecc", False)

        # Phase 1 a dit PENDING ou REJECTED_OLD_CHEQUE (QR non trouvé par cv2)
        # ET Phase 2 a confirmé QR pecc.tn valide → correction
        if p1_decision in ("PENDING_REVIEW", "REJECTED_OLD_CHEQUE") and p2_qr_valide:

            logger.warning("qr_sync_correction",
                           cheque_id=cheque_id,
                           p1_decision_avant=p1_decision,
                           p2_qr_lu=True,
                           note="cv2 a raté le QR que QReader a trouvé → correction décision Phase 1")

            # Corriger la DÉCISION Phase 1 :
            # Le chèque A un QR pecc.tn → c'est bien un nouveau chèque BCT 2025
            p1.details["decision"]         = "VALID_CHEQUE"
            p1.details["qr_sync_correction"] = True
            p1.details["qr_sync_note"]     = (
                "QR non détecté par cv2 mais confirmé par QReader AI (Phase 2). "
                "C'est un vrai nouveau chèque tunisien post-2025.")
            p1.passed = True

            # Mettre à jour la feature qr_present pour cohérence du rapport
            if "ml" in p1.details:
                p1.details["ml"]["features_xgb"]["qr_present"] = 1.0

            result.phases["identification"] = p1

            logger.info("qr_sync_decision_corrigee",
                        cheque_id=cheque_id,
                        decision_finale="VALID_CHEQUE",
                        note="Phase 1 cohérente avec Phase 2")

    except Exception as _e:
        logger.warning("qr_sync_erreur", error=str(_e)[:80])
    # ═══════════════════════════════════════════════════════════════

    result.phases["compliance"] = p2
    result.phases["ocr"]        = p3

    # ── Enrichissement Phase 3 depuis QR Phase 2 ─────────────────
    # (Banque depuis RIB, CMC7 construit, après les 2 phases parallèles)
    _tireur_physique = ""   # tireur extrait physiquement (avant fallback QR)
    try:
        qr_data = (p2.details or {}).get("qr_data", {}) or {}
        ext = p3.details.get("extracted", {})
        rib_qr = _re.sub(r'\s', '', qr_data.get("rib", "") or "")
        num_qr = _re.sub(r'\s', '', qr_data.get("numero_cheque", "") or "")
        # Banque depuis les 2 premiers chiffres du RIB
        if rib_qr and not ext.get("banque"):
            code = rib_qr[:2]
            ext["banque"] = RIB_BANK_MAP.get(code, f"Code banque {code}")
        # CMC7 = num_cheque + "1" + RIB (norme BCT)
        if num_qr and rib_qr and not ext.get("cmc7"):
            ext["cmc7"] = f"{num_qr}1{rib_qr}"
        # Sauvegarder le tireur extrait physiquement AVANT le fallback QR
        _tireur_physique = (ext.get("tireur") or "").strip()
        # Tireur QR = source de vérité → fallback si OCR absent OU garbage (sim < 30%)
        _tireur_qr_early = (qr_data.get("beneficiaire") or "").strip()
        if _tireur_qr_early:
            from difflib import SequenceMatcher as _SM
            _sim_early = _SM(None, _tireur_physique.upper(),
                             _tireur_qr_early.upper()).ratio() if _tireur_physique else 0.0
            if not _tireur_physique or _sim_early < 0.30:
                ext["tireur"]    = _tireur_qr_early
                ext["titulaire"] = _tireur_qr_early
                logger.info("tireur_qr_fallback",
                            ocr=_tireur_physique[:30], qr=_tireur_qr_early[:30],
                            sim=round(_sim_early, 2))
        p3.details["extracted"] = ext
    except Exception as _e:
        logger.warning("enrichissement_p3_erreur", error=str(_e)[:60])

    # ── Post-hoc : Tireur physique vs QR → injecté dans tableau Phase 2 ──
    try:
        def _normalize_tireur(name: str) -> str:
            """
            Normalise le nom tireur avant comparaison QR vs OCR.
            QR pecc.tn : "MR.CHERGUI HICHEM AG 23A MAGHR" → "CHERGUI HICHEM"
            OCR Phase3 : "CHERGUI HICHEM AG 23A MAGHR"    → "CHERGUI HICHEM"
            Règle : supprimer préfixes civils + ne garder que les 2 premiers mots alphabétiques
            """
            if not name:
                return ""
            t = name.strip().upper()
            # Supprimer préfixes civils (MR., MME., M., STE, SOCIETE, ETS, etc.)
            t = _re.sub(r'^(?:MR\.?|MME\.?|M\.?|SOCIETE|STE\.?|ETS\.?|SARL|SA|SNC)\s*', '', t)
            # Garder uniquement les tokens purement alphabétiques (nom + prénom)
            tokens = [tok for tok in t.split() if _re.match(r'^[A-ZÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ]{2,}$', tok)]
            # Prendre les 2 premiers mots significatifs (nom de famille + prénom)
            return ' '.join(tokens[:2])

        tireur_qr = (qr_data.get("beneficiaire") or "").strip()

        # Toujours ajouter la ligne de comparaison si on a au moins un côté
        if tireur_qr or _tireur_physique:
            from difflib import SequenceMatcher
            norm_qr  = _normalize_tireur(tireur_qr)
            norm_ocr = _normalize_tireur(_tireur_physique)

            if norm_qr and norm_ocr:
                sim = round(SequenceMatcher(None, norm_qr, norm_ocr).ratio(), 3)
                status = "OK" if sim >= 0.65 else "WARN_TITULAIRE"
            elif tireur_qr and not _tireur_physique:
                sim, status = 0.0, "OCR_ABSENT"
            elif _tireur_physique and not tireur_qr:
                sim, status = 0.0, "QR_ABSENT"
            else:
                sim, status = 0.0, "BOTH_ABSENT"

            row = {
                "champ":      "Titulaire (tireur)",
                "qr":         tireur_qr   or "(non disponible)",
                "qr_norm":    norm_qr     or "(non disponible)",
                "ocr":        _tireur_physique or "(non disponible)",
                "ocr_norm":   norm_ocr    or "(non disponible)",
                "status":     status,
                "detail":     f"sim={sim:.0%}" if norm_qr and norm_ocr else status,
                "match":      status == "OK",
            }
            logger.info("tireur_comparaison",
                        qr=tireur_qr[:30], ocr=_tireur_physique[:30],
                        norm_qr=norm_qr, norm_ocr=norm_ocr,
                        sim=sim, status=status)

            comp_qr_ph = (p2.details or {}).get("comparaison_qr_vs_physique", {})
            tableau = comp_qr_ph.get("tableau", [])
            # Remplacer si déjà présent, sinon ajouter
            tableau = [r for r in tableau if not r.get("champ", "").startswith("Titulaire")]
            tableau.append(row)
            if p2.details:
                if "comparaison_qr_vs_physique" not in p2.details:
                    p2.details["comparaison_qr_vs_physique"] = {"tableau": []}
                p2.details["comparaison_qr_vs_physique"]["tableau"] = tableau

    except Exception as _e:
        logger.warning("tireur_post_hoc_erreur", error=str(_e)[:60])

    # ── Phase 4 ──────────────────────────────────────────────────
    t4 = time.time()
    try:
        ext     = p3.details.get("extracted", {})
        qr_data = (p2.details or {}).get("qr_data", {}) or {}
        # Priorité : RIB QR (validé Luhn Phase 2) > RIB OCR (souvent mal extrait)
        rib_p4  = _re.sub(r'\s', '', qr_data.get("rib", "") or "") or ext.get("rib") or ""
        name_p4 = ext.get("titulaire") or qr_data.get("beneficiaire") or None
        p4 = await app.state.phase4.verify(
            recto_bytes=recto_bytes,
            cheque_id=cheque_id,
            rib =rib_p4,
            name=name_p4,
        )
    except Exception as e:
        p4 = _err("signature", e, int((time.time()-t4)*1000))
    p4.duration_ms = int((time.time()-t4)*1000)
    result.phases["signature"] = p4
    logger.info("phase4_done", decision=p4.details.get("decision"),
                score=round(p4.score, 3), ms=p4.duration_ms)

    result.final_decision = _decide(result)
    result.total_time_ms  = int((time.time()-t0)*1000)

    logger.info("pipeline_done", cheque_id=cheque_id,
                decision=result.final_decision,
                montant=p3.details.get("extracted",{}).get("montant_chiffres"),
                ms=result.total_time_ms)

    # Afficher rapport
    try:
        rapport = format_rapport(_sanitize(result.to_dict()))
        print(rapport)
    except Exception as e:
        logger.warning("format_rapport_erreur", error=str(e)[:60])

    _persister(cheque_id, result)
    return JSONResponse(content=_sanitize(result.to_dict()))


# ── Persistance ──────────────────────────────────────────────────
def _persister(cheque_id, result):
    try:
        decision = result.final_decision or "PENDING_MANUAL_REVIEW"
        with db_engine.connect() as conn:
            conn.execute(text(
                "UPDATE cheques SET decision_finale=:d WHERE id=:id"),
                {"d": decision, "id": cheque_id})
            for nom, p in result.phases.items():
                conn.execute(text("""
                                  INSERT INTO ai_results
                                      (cheque_id, phase, score, passed, details, duration_ms)
                                  VALUES (:cid, :ph, :sc, :pa, :de::jsonb, :du)
                                      ON CONFLICT (cheque_id, phase) DO UPDATE SET
                                      score=EXCLUDED.score, passed=EXCLUDED.passed,
                                                                            details=EXCLUDED.details, duration_ms=EXCLUDED.duration_ms
                                  """), {
                                 "cid": cheque_id, "ph": nom,
                                 "sc":  float(p.score) if p.score else 0.0,
                                 "pa":  p.passed,
                                 "de":  json.dumps(_sanitize(p.details)),
                                 "du":  p.duration_ms
                             })
            conn.commit()
    except Exception as e:
        logger.error("db_error", cheque_id=cheque_id, error=str(e)[:60])


# ── Health Check ─────────────────────────────────────────────────
@app.get("/api/ai/health")
async def health():
    p3 = getattr(app.state, "phase3", None)
    p4 = getattr(app.state, "phase4", None)

    return {
        "status": "ok",
        "version": "2.2.0",
        "db": test_connexion(),
        "phases": {
            "p1": getattr(app.state, "phase1", None) is not None,
            "p2": getattr(app.state, "phase2", None) is not None,
            "p3": p3 is not None,
            "p4": p4 is not None,
        },
        # Phase 3 — Cascade OCR
        "phase3_cascade": {
            "ocrspace":   True,
            "paddle":     getattr(p3, "use_paddle",  False) if p3 else False,
            "mistral":    getattr(p3, "use_mistral", False) if p3 else False,
            "trocr":      getattr(p3, "use_trocr",   False) if p3 else False,
            "qwen":       bool(os.getenv("OPENROUTER_API_KEY")),
            "gemini":     bool(os.getenv("GEMINI_API_KEY")),
            "claude":     bool(os.getenv("ANTHROPIC_API_KEY")),
        },
        # Phase 4
        "phase4_sig": {
            "siamese": p4.model is not None     if p4 else False,
            "cache":   len(p4._embedding_cache) if p4 else 0,
        },
    }


# ── Enrollment signature ─────────────────────────────────────────
DB_SIGNATURES_DIR = Path(__file__).resolve().parent.parent / "database_signatures"

@app.post("/api/ai/specimens/enroll")
async def enroll(
    user_id: str = Form(...),
    rib: str = Form(default=""),
    full_name: str = Form(default=""),
    signature: UploadFile = File(...)
):
    """
    Enrôle un spécimen de signature pour un titulaire.
    - user_id   : UUID du titulaire (obligatoire)
    - rib       : RIB 20 chiffres (recommandé — permet lookup Phase 4 par RIB)
    - full_name : Nom complet (facultatif, pour debug)
    - signature : Image de la signature (JPEG / PNG)
    """
    import re as _re2
    img_bytes = await signature.read()
    rib_clean = _re2.sub(r"[^0-9]", "", rib)

    # ── Sauvegarde dans database_signatures/{rib}.jpg uniquement ────
    DB_SIGNATURES_DIR.mkdir(parents=True, exist_ok=True)
    filename  = f"{rib_clean}.jpg" if rib_clean else f"spec_{user_id}_{int(time.time())}.jpg"
    p         = DB_SIGNATURES_DIR / filename
    db_sig_path = str(p)
    with open(p, "wb") as f:
        f.write(img_bytes)

    # ── Insertion en base specimens_signatures ────────────────────
    db_ok = False
    try:
        with db_engine.connect() as conn:
            conn.execute(text("""
                INSERT INTO specimens_signatures
                    (rib, user_id, full_name, image_path, enrolled_by)
                VALUES
                    (:rib, :uid, :name, :path, 'KYC_FLOW')
            """), {"rib": rib_clean or None, "uid": user_id,
                   "name": full_name, "path": db_sig_path})
            conn.commit()
        db_ok = True
    except Exception as e:
        logger.warning("enroll_db_failed", error=str(e)[:80])

    logger.info("specimen_enrolled", user_id=user_id, rib=rib_clean,
                name=full_name, db=db_ok)
    return {
        "status":   "enrolled",
        "path":     str(p),
        "rib":      rib_clean or None,
        "db_saved": db_ok,
    }


# ── Lancement ────────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8083, reload=True)