"""
app/phases/cheque_feature_extractor.py
========================================
Extracteur de features v5 — Structure chèque uniquement.

RESPONSABILITÉ UNIQUE :
  Répondre à : "Cette image a-t-elle la structure d'un chèque ?"
  PAS : "Est-il imprimé ?" (→ PrintDetector)
  PAS : "A-t-il un QR ?" (→ QRValidator — déjà dans Phase 1)

8 FEATURES STRUCTURELLES :
  1. ratio_wh          → format paysage (1.7-2.8 pour un chèque)
  2. qr_present        → QR pecc.tn détecté (4 passes)
  3. nb_lignes_horiz   → lignes de saisie (montant, bénéficiaire)
  4. densite_bas       → zone CMC7/MICR en bas
  5. ratio_blanc       → espace blanc (fond du chèque)
  6. variance          → complexité visuelle
  7. symetrie_h        → symétrie horizontale du document
  8. ratio_bords       → présence d'un cadre rectangulaire

NOTE SUR qr_present :
  Score 1.0 → nouveau chèque avec QR → fort signal REAL
  Score 0.0 → vieux chèque OU non-chèque → signal neutre
              (la distinction vieux/nouveau appartient à Phase 2)

NORMALISATION :
  Toutes les features calculées sur image normalisée
  → Robuste aux photos sombres et scans mal calibrés
"""

import cv2
import numpy as np
import logging
from typing import Dict

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    logger = logging.getLogger(__name__)


class ChequeFeatureExtractor:

    def __init__(self):
        self.qr_detector = cv2.QRCodeDetector()
        logger.info("feature_extractor_ready", nb_features=8)

    # ── Normalisation ─────────────────────────────────────────────────────

    def _norm(self, img: np.ndarray) -> np.ndarray:
        lum = float(img.mean())
        if lum < 100:
            img = np.clip(img.astype(np.float32) * (150/max(lum,1)),
                          0, 255).astype(np.uint8)
        return cv2.createCLAHE(3.0,(8,8)).apply(img)

    # ── Extraction ────────────────────────────────────────────────────────

    def extract(self, image_bytes: bytes) -> Dict[str, float]:
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
        if img is None:
            return self._zero()
        h, w     = img.shape
        img_n    = self._norm(img)
        return {
            "ratio_wh":        float(w)/max(h,1),
            "qr_present":      self._qr(arr),
            "nb_lignes_horiz": self._lignes(img_n, w),
            "densite_bas":     float(np.sum(img_n[int(h*.85):]<128)) /
                               max(img_n[int(h*.85):].size,1),
            "ratio_blanc":     float(np.mean(img_n>180)),
            "variance":        min(float(np.var(img_n))/1000.0, 5.0),
            "symetrie_h":      self._sym(img_n, w),
            "ratio_bords":     self._bords(img_n),
        }

    def extract_as_vector(self, image_bytes: bytes) -> np.ndarray:
        f = self.extract(image_bytes)
        return np.array([f[k] for k in self.feature_names()], dtype=np.float32)

    @staticmethod
    def feature_names() -> list:
        return ["ratio_wh","qr_present","nb_lignes_horiz",
                "densite_bas","ratio_blanc","variance",
                "symetrie_h","ratio_bords"]

    # ── Features ─────────────────────────────────────────────────────────

    def _qr(self, arr: np.ndarray) -> float:
        """4 passes cohérentes avec qr_validator."""
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None: return 0.0
        h, w  = img.shape[:2]
        gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        enh   = cv2.createCLAHE(3.0,(8,8)).apply(gray)
        passes = [
            img,
            cv2.cvtColor(enh, cv2.COLOR_GRAY2BGR),
            cv2.resize(img,(w*2,h*2),interpolation=cv2.INTER_CUBIC),
            cv2.resize(img,(w*3,h*3),interpolation=cv2.INTER_CUBIC),
        ]
        for p in passes:
            try:
                _, pts, _ = self.qr_detector.detectAndDecode(p)
                if pts is not None and len(pts)>0:
                    if float(np.linalg.norm(pts[0][0]-pts[0][1]))>10:
                        return 1.0
            except Exception: continue
        return 0.0

    def _lignes(self, img: np.ndarray, w: int) -> float:
        edges = cv2.Canny(img, 30, 100)
        lines = cv2.HoughLinesP(edges,1,np.pi/180,60,
                                minLineLength=int(w*.35),maxLineGap=40)
        if lines is None: return 0.0
        h = [l for l in lines if abs(l[0][1]-l[0][3])<12]
        return min(float(len(h))/10.0, 1.0)

    def _sym(self, img: np.ndarray, w: int) -> float:
        mid = w//2
        l   = img[:,:mid].astype(np.float32)
        r   = np.fliplr(img[:,mid:mid*2]).astype(np.float32)
        if l.size==0 or r.size==0: return 0.0
        return max(0.0, 1.0-np.mean(np.abs(l-r))/128.0)

    def _bords(self, img: np.ndarray) -> float:
        b = np.concatenate([img[:5,:].flatten(), img[-5:,:].flatten(),
                            img[:,:5].flatten(), img[:,-5:].flatten()])
        return float(np.mean(b<100)) if b.size>0 else 0.0

    @staticmethod
    def _zero() -> Dict[str, float]:
        return {k:0.0 for k in ChequeFeatureExtractor.feature_names()}

    def interpret(self, f: Dict[str, float]) -> str:
        s = []
        if f["ratio_wh"] < 1.5:   s.append("ratio_faible({:.2f})".format(f["ratio_wh"]))
        if f["ratio_wh"] > 3.0:   s.append("ratio_eleve({:.2f})".format(f["ratio_wh"]))
        if f["qr_present"] < 0.5: s.append("sans_qr")
        if f["nb_lignes_horiz"] < 0.1: s.append("sans_lignes")
        if f["ratio_blanc"] < 0.25:    s.append("image_sombre")
        return " | ".join(s) if s else "structure_correcte"