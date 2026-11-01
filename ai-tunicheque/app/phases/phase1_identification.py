"""
app/phases/phase1_identification.py — CORRIGÉ v4 FINAL
FIX : _load_cnn() avec 5 stratégies compatibilité Keras 2.x/3.x
"""

import sys, os, cv2, json, logging, pickle, time
from enum import Enum
from pathlib import Path
import numpy as np
import tensorflow as tf

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

from app.models.pipeline_models          import PhaseResult
from app.phases.qr_validator             import QRValidator
from app.phases.print_detector           import PrintDetector
from app.phases.cheque_feature_extractor import ChequeFeatureExtractor


def _apply_exif_rotation(image_bytes: bytes) -> bytes:
    """
    Applique la rotation EXIF via Pillow avant de passer à OpenCV.
    cv2.imdecode ignore les tags EXIF — une photo prise en portrait sur
    Android arrive avec les pixels en paysage + tag orientation=6.
    Sans ce fix, le chèque apparaît de côté et l'OCR échoue.
    """
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


class ImageSource(str, Enum):
    MOBILE  = "mobile"
    SCANNER = "scanner"

PROFILES = {
    ImageSource.MOBILE: {
        "blur_min": 8.0, "ratio_min": 0.3, "ratio_max": 8.0,
        "width_min": 200, "height_min": 80,
        "threshold_real": 0.70, "threshold_fake": 0.50, "threshold_xgb": 0.40,
        "check_printed": True,
        "messages": {
            "VALID_CHEQUE":            {"titre": "Chèque accepté",            "detail": "Chèque authentique pecc.tn — vérification en cours.", "action": "Traitement Phase 2..."},
            "REJECTED_NOT_A_CHEQUE":   {"titre": "Document non reconnu",      "detail": "Ce document n'est pas un chèque bancaire tunisien.",   "action": "Vérifiez que vous photographiez le RECTO du chèque en mode PAYSAGE."},
            "REJECTED_PRINTED_CHEQUE": {"titre": "Chèque imprimé détecté",    "detail": "Ce chèque semble imprimé sur imprimante ordinaire.",    "action": "Contactez votre banque pour un carnet de chèques officiel."},
            "REJECTED_OLD_CHEQUE":     {"titre": "Chèque non valide",         "detail": "Ce chèque ne contient pas le QR code pecc.tn requis.",  "action": "Ce chèque est trop ancien. Contactez votre banque."},
            "PENDING_REVIEW":          {"titre": "Vérification en cours",     "detail": "Votre chèque nécessite une vérification manuelle.",     "action": "Un agent analysera votre chèque dans les plus brefs délais."},
        }
    },
    ImageSource.SCANNER: {
        "blur_min": 20.0, "ratio_min": 0.3, "ratio_max": 8.0,
        "width_min": 300, "height_min": 100,
        "threshold_real": 0.70, "threshold_fake": 0.50, "threshold_xgb": 0.40,
        "check_printed": False,
        "messages": {
            "VALID_CHEQUE":            {"titre": "Chèque valide",              "detail": "Chèque authentique pecc.tn — Phase 2 en cours.", "action": "Continuer"},
            "REJECTED_NOT_A_CHEQUE":   {"titre": "Document non reconnu",       "detail": "Structure document incorrecte.",                 "action": "Vérifier physiquement. Contacter superviseur."},
            "REJECTED_PRINTED_CHEQUE": {"titre": "N/A (scanner)",              "detail": "Non applicable au scanner.",                    "action": ""},
            "REJECTED_OLD_CHEQUE":     {"titre": "QR pecc.tn absent",          "detail": "Chèque antérieur à 2025.",                      "action": "Informer le client. Chèque non accepté BCT."},
            "PENDING_REVIEW":          {"titre": "Vérification manuelle",      "detail": "Score ML ambigu.",                              "action": "Examiner physiquement. Escalader au superviseur."},
        }
    },
}


class ChequeIdentificationPhase:

    def __init__(self):
        self.cnn_model     = self._load_cnn()
        self.xgb_model     = self._load_xgb()
        self.xgb_scaler    = self._load_scaler()
        self.class_indices = self._load_class_indices()
        self.real_label    = self.class_indices.get("real", 1)
        self.feature_ext   = ChequeFeatureExtractor()
        self.qr_validator  = QRValidator()
        self.print_detector= PrintDetector()
        logger.info("phase1_ready", cnn=self.cnn_model is not None,
                    xgb=self.xgb_model is not None, real_label=self.real_label)
        logger.info("phase1_ready")

    # ═══════════════════════════════════════════════════════════════════════
    # FIX — _load_cnn() : 4 stratégies compatibilité Keras 2.x / 3.x
    # ═══════════════════════════════════════════════════════════════════════
    def _load_cnn(self):
        paths = [
            "saved_models/best_model_phaseA.keras",
            "saved_models/best_phaseA.keras",
            "saved_models/best_phaseB.keras",
            "saved_models/best_model_phaseA.h5",
            "saved_models/cheque_classifier_phase1.h5",
            "saved_models/best_model_phaseB.h5",
        ]
        for p in paths:
            if not Path(p).exists():
                continue
            try:
                import tf_keras
                m = tf_keras.models.load_model(p, compile=False)
                logger.info("cnn_loaded_tf_keras", path=p)
                return m
            except ImportError:
                pass  # tf-keras pas installé → continuer
            except Exception as e0:
                logger.warning("cnn_s0_fail", path=p, error=str(e0)[:100])

# Stratégie 1 : standard
            try:
                m = tf.keras.models.load_model(p, compile=False)
                logger.info("cnn_loaded_standard", path=p)
                return m
            except Exception as e1:
                logger.warning("cnn_s1_fail", path=p, error=str(e1)[:100])
            # Stratégie 2 : safe_mode=False (Keras 3)
            try:
                m = tf.keras.models.load_model(p, compile=False, safe_mode=False)
                logger.info("cnn_loaded_safe_mode", path=p)
                return m
            except Exception as e2:
                logger.warning("cnn_s2_fail", path=p, error=str(e2)[:100])
            # Stratégie 3 : custom_objects pour InputLayer incompatible
            try:
                from tensorflow.keras.layers import InputLayer as _IL
                class CompatInputLayer(_IL):
                    def __init__(self, *args, **kwargs):
                        kwargs.pop("batch_shape", None)
                        kwargs.pop("optional", None)
                        super().__init__(*args, **kwargs)
                m = tf.keras.models.load_model(p, compile=False,
                                               custom_objects={"InputLayer": CompatInputLayer})
                logger.info("cnn_loaded_compat", path=p)
                return m
            except Exception as e3:
                logger.warning("cnn_s3_fail", path=p, error=str(e3)[:100])
            # Stratégie 4 : reconstruction MobileNetV2 + chargement poids
            try:
                arch = self._build_cnn_architecture()
                if arch:
                    arch.load_weights(p)
                    logger.info("cnn_loaded_weights", path=p)
                    return arch
            except Exception as e4:
                logger.warning("cnn_s4_fail", path=p, error=str(e4)[:100])

        logger.error("cnn_load_all_failed", note="XGBoost seul — Phase 1 reste fonctionnelle")
        return None

    def _build_cnn_architecture(self):
        """Reconstruction MobileNetV2 pour chargement poids seuls."""
        try:
            base = tf.keras.applications.MobileNetV2(
                input_shape=(224, 224, 3), include_top=False, weights=None)
            x   = tf.keras.layers.GlobalAveragePooling2D()(base.output)
            x   = tf.keras.layers.Dense(128, activation="relu")(x)
            x   = tf.keras.layers.Dropout(0.3)(x)
            out = tf.keras.layers.Dense(2, activation="softmax")(x)
            return tf.keras.Model(inputs=base.input, outputs=out)
        except Exception as e:
            logger.warning("cnn_rebuild_failed", error=str(e))
            return None

    def _load_xgb(self):
        p = Path("saved_models/xgboost_cheque.pkl")
        if not p.exists():
            logger.warning("xgb_not_found"); return None
        try:
            with open(p, "rb") as f: m = pickle.load(f)
            logger.info("xgb_loaded"); return m
        except Exception as e:
            logger.error("xgb_load_error", error=str(e)); return None

    def _load_scaler(self):
        p = Path("saved_models/xgboost_scaler.pkl")
        if not p.exists(): return None
        try:
            with open(p, "rb") as f: return pickle.load(f)
        except Exception: return None

    def _load_class_indices(self) -> dict:
        p = Path("saved_models/class_indices.json")
        if p.exists():
            try:
                with open(p) as f: return json.load(f)
            except Exception: pass
        return {"real": 1, "fake": 0}

    def _normaliser(self, image_bytes: bytes) -> bytes:
        try:
            # Apply EXIF orientation first (cv2.imdecode ignores EXIF tags)
            image_bytes = _apply_exif_rotation(image_bytes)

            arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None: return image_bytes
            h, w = img.shape[:2]
            if h > w * 1.1:
                img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
                h, w = img.shape[:2]
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            lum  = float(gray.mean())
            if lum < 80:
                img = np.clip(img.astype(np.float32) * (150 / max(lum, 1)), 0, 255).astype(np.uint8)
            if lum < 160:
                lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
                l, a, b = cv2.split(lab)
                l = cv2.createCLAHE(2.5, (8, 8)).apply(l)
                img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 93])
            return buf.tobytes()
        except Exception as e:
            logger.warning("normalisation_error", error=str(e))
            return image_bytes

    def _check_quality(self, image_bytes: bytes, profile: dict) -> dict:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None: return {"ok": False, "raison": "IMAGE_ILLISIBLE"}
        h, w  = img.shape
        ratio = float(w) / h if h > 0 else 0
        if not (profile["ratio_min"] <= ratio <= profile["ratio_max"]):
            return {"ok": False, "raison": "RATIO_INVALIDE", "detail": "ratio={:.2f}".format(ratio)}
        if w < profile["width_min"] or h < profile["height_min"]:
            return {"ok": False, "raison": "RESOLUTION_INSUFFISANTE", "detail": "{}x{}".format(w, h)}
        blur = float(cv2.Laplacian(img, cv2.CV_64F).var())
        if blur < profile["blur_min"]:
            return {"ok": False, "raison": "IMAGE_FLOUE", "blur": round(blur, 1)}
        return {"ok": True, "blur": round(blur, 1), "dim": "{}x{}".format(w, h), "ratio": round(ratio, 2)}

    def _cnn_score(self, image_bytes: bytes) -> float:
        if self.cnn_model is None: return 0.5
        try:
            arr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None: return 0.5
            img = cv2.cvtColor(cv2.resize(img, (224, 224), interpolation=cv2.INTER_AREA),
                               cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
            raw = float(self.cnn_model.predict(np.expand_dims(img, 0), verbose=0)[0][0])
            return round(raw if self.real_label == 1 else 1.0 - raw, 4)
        except Exception as e:
            logger.warning("cnn_predict_error", error=str(e)); return 0.5

    def _xgb_score(self, image_bytes: bytes) -> float:
        if self.xgb_model is None: return 0.5
        try:
            f = self.feature_ext.extract_as_vector(image_bytes).reshape(1, -1)
            if self.xgb_scaler: f = self.xgb_scaler.transform(f)
            return round(float(self.xgb_model.predict_proba(f)[0][1]), 4)
        except Exception as e:
            logger.warning("xgb_error", error=str(e)); return 0.5

    def _vote(self, cnn: float, xgb: float, profile: dict) -> dict:
        tr, tf_, tx = profile["threshold_real"], profile["threshold_fake"], profile["threshold_xgb"]
        cr = cnn >= tr; cf = cnn < tf_; cp = not cr and not cf; xr = xgb >= tx
        if   cr and xr:     d, r = "REAL",    "accord_REAL"
        elif cf and not xr: d, r = "FAKE",    "accord_FAKE"
        elif cr and not xr: d, r = "PENDING", "CNN_REAL_XGB_FAKE"
        elif cf and xr:     d, r = "PENDING", "CNN_FAKE_XGB_REAL"
        elif cp and xr:     d, r = "PENDING", "CNN_PEND_XGB_REAL"
        else:               d, r = "FAKE",    "CNN_PEND_XGB_FAKE"
        return {"decision": d, "raison": r, "cnn": cnn, "xgb": xgb,
                "score_final": round((cnn + xgb) / 2, 4)}

    def _result(self, decision: str, score: float, ms: int,
                source: ImageSource, profile: dict, extra: dict) -> PhaseResult:
        msg    = profile["messages"].get(decision, profile["messages"]["PENDING_REVIEW"])
        passed = decision in ("VALID_CHEQUE", "PENDING_REVIEW")
        return PhaseResult(
            phase="identification", score=score, passed=passed, duration_ms=ms,
            details={"decision": decision, "source": source.value,
                     "message": {"titre": msg["titre"], "detail": msg["detail"],
                                 "action": msg["action"]}, **extra})

    async def analyze(self, recto_bytes: bytes, verso_bytes: bytes,
                      cheque_id: str, source: ImageSource = ImageSource.MOBILE) -> PhaseResult:
        t0      = time.time()
        profile = PROFILES[source]
        ms      = lambda: int((time.time() - t0) * 1000)

        logger.info("phase1_start", cheque_id=cheque_id, source=source.value)

        recto = self._normaliser(recto_bytes)
        verso = self._normaliser(verso_bytes) if verso_bytes else None

        q = self._check_quality(recto, profile)
        if not q["ok"]:
            return self._result("PENDING_REVIEW", 0.0, ms(), source, profile,
                                {"quality": q, "info": "qualite_insuffisante_agent_requis"})

        cnn      = self._cnn_score(recto)
        xgb      = self._xgb_score(recto)
        features = self.feature_ext.extract(recto)
        vote     = self._vote(cnn, xgb, profile)

        ml_info = {
            "cnn_score":      cnn,
            "xgb_score":      round(xgb, 4),
            "vote":           vote,
            "features_xgb":   features,
            "interpretation": self.feature_ext.interpret(features),
            "mode":           "hybride" if self.xgb_model else "xgb_seul",
        }
        logger.info("q1_result", cheque_id=cheque_id, vote=vote["decision"], cnn=cnn, xgb=round(xgb, 4))

        if vote["decision"] == "FAKE":
            return self._result("REJECTED_NOT_A_CHEQUE", vote["score_final"],
                                ms(), source, profile, {"ml": ml_info})
        if vote["decision"] == "PENDING":
            return self._result("PENDING_REVIEW", vote["score_final"],
                                ms(), source, profile, {"ml": ml_info})

        # Q2 — Imprimé ? (RECTO + VERSO)
        if profile["check_printed"]:
            pr = self.print_detector.analyze(recto, verso)
            logger.info("q2_result", cheque_id=cheque_id, decision=pr.decision,
                        fft=pr.scores.get("fft", 0), lbp=pr.scores.get("lbp", 0),
                        verso_analyse=pr.scores.get("verso_disponible", False))
            if pr.is_printed:
                fft_score = pr.scores.get("fft", 0)
                if fft_score < 0.1 and cnn >= 0.90:
                    logger.warning("q2_printed_override_par_cnn", cheque_id=cheque_id)
                else:
                    return self._result("REJECTED_PRINTED_CHEQUE", vote["score_final"],
                                        ms(), source, profile,
                                        {"ml": ml_info, "print_detection": {
                                            "decision": pr.decision, "confidence": pr.confidence,
                                            "scores": pr.scores, "message": pr.message,
                                            "verso_analyse": pr.scores.get("verso_disponible", False)}})
        else:
            pr = None

        # Q3 — QR pecc.tn ?
        qr = self.qr_validator.check(recto)
        logger.info("q3_result", cheque_id=cheque_id, qr_found=qr.found,
                    qr_readable=bool(qr.data and not qr.data.startswith("(QR")))

        if not qr.found:
            return self._result("REJECTED_OLD_CHEQUE", vote["score_final"],
                                ms(), source, profile,
                                {"ml": ml_info, "qr_code": {
                                    "found": False,
                                    "message": "Aucun QR pecc.tn — chèque antérieur à 2025"}})

        if not qr.data or qr.data.startswith("(QR"):
            logger.warning("q3_qr_illisible", cheque_id=cheque_id)
            return self._result("PENDING_REVIEW", vote["score_final"],
                                ms(), source, profile,
                                {"ml": ml_info, "qr_code": {
                                    "found": True, "data": qr.data,
                                    "message": "QR présent mais non lisible — agent requis"}})

        logger.info("phase1_valid", cheque_id=cheque_id,
                    score=vote["score_final"], duration_ms=ms())
        return self._result("VALID_CHEQUE", vote["score_final"],
                            ms(), source, profile,
                            {"ml": ml_info,
                             "qr_code": {"found": True, "data": qr.data, "message": qr.message},
                             "quality": q,
                             "print_detection": {
                                 "decision":      pr.decision   if pr else "N/A",
                                 "confidence":    pr.confidence if pr else 1.0,
                                 "verso_analyse": pr.scores.get("verso_disponible", False) if pr else False}})