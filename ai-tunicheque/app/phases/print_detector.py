"""
app/phases/print_detector.py
==============================
Détecteur de chèques imprimés — Recto + Verso.

OBJECTIF PHASE 1 :
  Détecter si le chèque est IMPRIMÉ sur imprimante ordinaire (fraude)
  vs AUTHENTIQUE (papier bancaire BCT sécurisé).
  Valable pour : mobile ET scanner / recto ET verso.

MÉTHODES :
  ┌─────────────────────────────────────────────────────┐
  │  RECTO  : FFT + LBP + INK  (analyse physique)       │
  │  VERSO  : FFT + LBP        (analyse physique 60%)   │
  │  VERSO  : One-Class SVM    (CNN features ImageNet)   │
  └─────────────────────────────────────────────────────┘

PRINCIPE DÉTECTION :
  Vrai chèque BCT   → papier sécurisé → filigrane → texture complexe
  Chèque imprimé A4 → papier lisse    → pas de filigrane → texture uniforme

  FFT        : tramage imprimante (pics périodiques spectre fréquentiel)
  LBP        : texture papier (entropie faible = A4 lisse)
  INK        : uniformité encre (toner laser = très uniforme)
  One-Class  : CNN features MobileNetV2 — entraîné sur "vrai" seulement
               → toute anomalie = imprimé (100% de détection imprimés)

MODÈLES VERSO (chargé par priorité) :
  1. verso_oneclass.joblib  — One-Class SVM  cv=80%  ← PRIORITAIRE
  2. verso_cnn_svm.joblib   — CNN+SVM binaire
  3. verso_svm.joblib       — HOG+SVM binaire

DÉCISIONS : AUTHENTIC | PRINTED | UNCERTAIN
"""

import cv2
import numpy as np
import os
import logging
from dataclasses import dataclass
from typing import Dict, Optional

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class PrintDetectionResult:
    decision:   str
    is_printed: bool
    confidence: float
    scores:     Dict[str, float]
    message:    str


class PrintDetector:

    # ── Seuils analyse physique ────────────────────────────────────
    FFT_THRESHOLD = 0.45
    LBP_THRESHOLD = 0.80
    INK_THRESHOLD = 0.80

    def __init__(self):
        # ── Chargement modèle verso ML (priorité : oneclass > cnn > hog) ──
        self.svm_pipeline   = None
        self.svm_method     = None   # "oneclass" | "cnn" | "hog"
        self.svm_hog_params = None
        self.svm_img_size   = (128, 128)

        model_paths = [
            ("saved_models/verso_oneclass.joblib", "oneclass"),
            ("saved_models/verso_cnn_svm.joblib",  "cnn"),
            ("saved_models/verso_svm.joblib",       "hog"),
        ]

        for path, method in model_paths:
            if not os.path.exists(path):
                continue
            try:
                import joblib
                data    = joblib.load(path)
                cv_mean = data.get("cv_mean", 0.0)

                # Seuil minimum : oneclass accepté dès 0.60, autres 0.65
                seuil = 0.60 if method == "oneclass" else 0.65

                if cv_mean >= seuil:
                    self.svm_pipeline = data["pipeline"]
                    self.svm_method   = method
                    self.svm_img_size = data.get("img_size", (128, 128))

                    if method == "hog":
                        self.svm_hog_params = data.get("hog_params", {
                            "orientations":    9,
                            "pixels_per_cell": (8, 8),
                            "cells_per_block": (2, 2),
                            "block_norm":      "L2-Hys",
                            "channel_axis":    -1,
                        })

                    logger.info("svm_verso_charge",
                                path=path,
                                method=method,
                                cv_accuracy=f"{cv_mean:.0%}")
                    break
                else:
                    logger.info("svm_verso_skip",
                                path=path,
                                cv=f"{cv_mean:.0%}",
                                note="Précision insuffisante — ignoré")

            except Exception as e:
                logger.warning("svm_verso_erreur",
                               path=path, error=str(e)[:100])

        if self.svm_pipeline is None:
            logger.info("svm_verso_absent",
                        note="Analyse physique seule (FFT+LBP+INK)")

        logger.info("print_detector_ready",
                    verso_svm=self.svm_pipeline is not None,
                    method=self.svm_method)

    # ══════════════════════════════════════════════════════════════
    # POINT D'ENTRÉE PRINCIPAL
    # Appelé par Phase 1 pour recto ET verso
    # Source : mobile (photo) ou scanner
    # ══════════════════════════════════════════════════════════════

    def analyze(self, recto_bytes: bytes,
                verso_bytes: Optional[bytes] = None) -> PrintDetectionResult:
        """
        LOGIQUE DE VOTE :
          vote_fft : FFT recto+verso fusionnés
          vote_lbp : LBP recto+verso fusionnés
          vote_ink : INK recto (encre imprimée)
          vote_svm : One-Class SVM verso (si modèle disponible)

          >= 2 votes → PRINTED   (chèque imprimé = REJETÉ)
          == 1 vote  → UNCERTAIN (vérification manuelle)
          == 0 vote  → AUTHENTIC (vrai papier bancaire)
        """

        # ── RECTO — Analyse physique ───────────────────────────────
        arr   = np.frombuffer(recto_bytes, np.uint8)
        recto = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if recto is None:
            return PrintDetectionResult("UNCERTAIN", False, 0.0, {}, "illisible")

        recto  = self._norm(recto)
        fft_r  = self._fft(recto)
        lbp_r  = self._lbp(recto)
        ink_r  = self._ink(recto)

        # ── VERSO — Analyse physique (si disponible) ──────────────
        fft_v         = 0.0
        lbp_v         = 0.0
        verso_analyse = False

        if verso_bytes:
            arr_v = np.frombuffer(verso_bytes, np.uint8)
            verso = cv2.imdecode(arr_v, cv2.IMREAD_COLOR)
            if verso is not None:
                verso         = self._norm(verso)
                fft_v         = self._fft(verso)
                lbp_v         = self._lbp(verso)
                verso_analyse = True
                logger.info("verso_physique",
                            fft_v=round(fft_v, 3),
                            lbp_v=round(lbp_v, 3))

        # ── Fusion recto + verso ───────────────────────────────────
        # Verso = 60% car pas de texte → pas de faux positifs "encre"
        # Recto = 40%
        if verso_analyse:
            fft = fft_r * 0.4 + fft_v * 0.6
            lbp = lbp_r * 0.4 + lbp_v * 0.6
        else:
            fft, lbp = fft_r, lbp_r
        ink = ink_r

        # ── Votes physiques ────────────────────────────────────────
        votes = sum([
            fft > self.FFT_THRESHOLD,
            lbp > self.LBP_THRESHOLD,
            ink > self.INK_THRESHOLD,
            ])

        # ── VERSO — Vote ML (One-Class SVM ou HOG+SVM) ────────────
        svm_score = None
        svm_vote  = 0

        if self.svm_pipeline is not None and verso_bytes is not None:
            if self.svm_method == "oneclass":
                svm_score, svm_vote = self._vote_oneclass(verso_bytes)
            else:
                svm_score, svm_vote = self._vote_svm_verso(verso_bytes)

            if svm_vote == 1:
                votes += 1
                logger.info("svm_vote_imprime", method=self.svm_method,
                            total_votes=votes)
            elif svm_vote == -1:
                if votes == 1:
                    votes = 0
                    logger.info("svm_annule_faux_positif",
                                method=self.svm_method)

        # ── Scores pour le rapport ─────────────────────────────────
        scores = {
            "fft":              round(fft,   3),
            "lbp":              round(lbp,   3),
            "ink":              round(ink,   3),
            "fft_recto":        round(fft_r, 3),
            "lbp_recto":        round(lbp_r, 3),
            "fft_verso":        round(fft_v, 3) if verso_analyse else None,
            "lbp_verso":        round(lbp_v, 3) if verso_analyse else None,
            "svm_score":        round(svm_score, 3) if svm_score is not None else None,
            "svm_method":       self.svm_method,
            "verso_disponible": verso_analyse,
            "svm_disponible":   self.svm_pipeline is not None,
        }

        # ── Décision finale ───────────────────────────────────────
        if votes >= 2:
            d   = "PRINTED"
            p   = True
            c   = (fft + lbp + ink) / 3
            msg = ("Chèque imprimé détecté "
                   "fft={:.2f} lbp={:.2f} ink={:.2f}{}").format(
                fft, lbp, ink,
                f" svm[{self.svm_method}]={svm_score:.2f}" if svm_score else "")
        elif votes == 1:
            d   = "UNCERTAIN"
            p   = False
            c   = 0.4
            msg = "Signal ambigu — vérification manuelle recommandée"
        else:
            d   = "AUTHENTIC"
            p   = False
            c   = 1.0 - (fft + lbp + ink) / 3
            msg = "Papier fiduciaire bancaire authentique"

        logger.info("print_detection",
                    decision=d, votes=votes,
                    fft=round(fft, 3),
                    lbp=round(lbp, 3),
                    ink=round(ink, 3),
                    verso=verso_analyse,
                    svm=self.svm_method)

        return PrintDetectionResult(d, p, round(c, 3), scores, msg)

    # ══════════════════════════════════════════════════════════════
    # VOTE ONE-CLASS SVM (nouveauté)
    # Entraîné sur "vrai" seulement → anomalie = imprimé
    # ══════════════════════════════════════════════════════════════

    def _vote_oneclass(self, verso_bytes: bytes):
        """
        One-Class SVM avec features CNN MobileNetV2.

        pred = +1 → normal (vrai chèque)
        pred = -1 → anomalie (imprimé ou différent)

        score_dec < -0.5  = anomalie très certaine → vote IMPRIMÉ
        score_dec >  0.3  = normal certain          → vote AUTHENTIQUE
        Entre les deux    = neutre (physique décide)
        """
        try:
            import tensorflow as tf

            arr = np.frombuffer(verso_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None, 0

            # Features CNN MobileNetV2 gelé (1280-dim)
            img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_res  = cv2.resize(img_rgb, (224, 224)).astype(np.float32)
            img_norm = (img_res / 127.5) - 1.0   # normalisation MobileNetV2
            batch    = np.expand_dims(img_norm, 0)

            base = tf.keras.applications.MobileNetV2(
                input_shape=(224, 224, 3),
                include_top=False,
                weights="imagenet",
            )
            base.trainable = False
            extr = tf.keras.Sequential([
                base,
                tf.keras.layers.GlobalAveragePooling2D(),
            ])
            feat     = extr.predict(batch, verbose=0)
            features = feat.reshape(1, -1).astype(np.float32)

            # Prédiction One-Class SVM
            pred      = self.svm_pipeline.predict(features)[0]
            score_dec = float(self.svm_pipeline.decision_function(features)[0])

            # Convertir score_dec en probabilité [0-1] via sigmoid
            score_auth = float(1 / (1 + np.exp(-score_dec)))

            logger.info("oneclass_svm_verso",
                        pred=int(pred),
                        score_dec=round(score_dec, 3),
                        decision="VRAI" if pred == 1 else "ANOMALIE_IMPRIME")

            # Seuil assoupli (évite les faux positifs)
            if pred == -1 and score_dec < -0.5:    # anomalie certaine
                return score_auth, 1               # vote IMPRIMÉ
            elif pred == 1 and score_dec > 0.3:    # normal certain
                return score_auth, -1              # vote AUTHENTIQUE
            return score_auth, 0                   # neutre

        except Exception as e:
            logger.warning("oneclass_erreur", error=str(e)[:100])
            return None, 0

    # ══════════════════════════════════════════════════════════════
    # VOTE HOG + SVM (fallback si oneclass absent)
    # ══════════════════════════════════════════════════════════════

    def _vote_svm_verso(self, verso_bytes: bytes):
        """
        HOG + SVM binaire (fallback).
        Retourne (score_authentique, vote).
        """
        try:
            from skimage.feature import hog as sk_hog
            from skimage.transform import resize as sk_resize

            arr  = np.frombuffer(verso_bytes, np.uint8)
            img  = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                return None, 0

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_res = sk_resize(img_rgb,
                                self.svm_img_size + (3,),
                                anti_aliasing=True,
                                preserve_range=False)

            features = sk_hog(img_res, **self.svm_hog_params)
            features = features.reshape(1, -1).astype(np.float32)

            pred  = self.svm_pipeline.predict(features)[0]
            proba = self.svm_pipeline.predict_proba(features)[0]

            # proba[0] = P(IMPRIMÉ), proba[1] = P(AUTHENTIQUE)
            score = float(proba[1])

            logger.info("svm_hog_verso",
                        score_authentique=round(score, 3),
                        decision="VRAI" if pred == 1 else "IMPRIME",
                        proba_imprime=round(float(proba[0]), 3))

            if pred == 0 and proba[0] > 0.65:
                return score, 1    # vote IMPRIMÉ
            elif pred == 1 and proba[1] > 0.85:
                return score, -1   # vote AUTHENTIQUE (fort)
            return score, 0        # neutre

        except ImportError:
            logger.warning("skimage_absent",
                           note="pip install scikit-image scikit-learn")
            return None, 0
        except Exception as e:
            logger.warning("svm_predict_erreur", error=str(e)[:100])
            return None, 0

    # ══════════════════════════════════════════════════════════════
    # MÉTHODES ANALYSE PHYSIQUE (INCHANGÉES)
    # ══════════════════════════════════════════════════════════════

    def _fft(self, img: np.ndarray) -> float:
        """FFT — détecte le tramage périodique de l'imprimante."""
        try:
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w  = gray.shape
            zone  = gray[int(h*.1):int(h*.5), int(w*.1):int(w*.9)]
            zone  = cv2.resize(zone, (256, 256))
            mag   = np.log1p(np.abs(np.fft.fftshift(
                np.fft.fft2(zone.astype(np.float32)))))
            mask  = np.ones_like(mag)
            cv2.circle(mask, (128, 128), 25, 0, -1)
            mhf   = mag * mask
            vals  = mhf[mhf > 0]
            if vals.size == 0: return 0.0
            seuil = vals.mean() + 2.5 * vals.std()
            return min(float(np.sum(mhf > seuil)) / 80.0, 1.0)
        except Exception: return 0.0

    def _lbp(self, img: np.ndarray) -> float:
        """LBP — texture papier fiduciaire vs A4."""
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            zones = [
                gray[int(h*.15):int(h*.35), int(w*.05):int(w*.45)],
                gray[int(h*.15):int(h*.35), int(w*.55):int(w*.95)],
            ]
            ents = []
            for z in zones:
                if z.size < 100: continue
                lbp_img = np.zeros_like(z)
                for i, ang in enumerate(
                        [2*np.pi*k/8 for k in range(8)]):
                    xo, yo = int(round(np.cos(ang))), int(round(-np.sin(ang)))
                    x1, y1 = max(0, -xo), max(0, -yo)
                    x2, y2 = min(w, w-xo), min(h, h-yo)
                    if y2-y1 > 0 and x2-x1 > 0:
                        nb = z[y1+yo:y2+yo, x1+xo:x2+xo]
                        ct = z[y1:y2, x1:x2]
                        if nb.shape == ct.shape:
                            lbp_img[y1:y2, x1:x2] += (
                                                             nb >= ct).astype(np.uint8) * (2**i)
                hst = np.bincount(lbp_img.flatten(),
                                  minlength=256).astype(float)
                hst /= hst.sum() + 1e-9
                e = -np.sum(hst[hst > 0] * np.log2(hst[hst > 0]))
                ents.append(e)
            if not ents: return 0.5
            return min(max(1.0-(np.mean(ents)-3.0)/4.0, 0.0), 1.0)
        except Exception: return 0.0

    def _ink(self, img: np.ndarray) -> float:
        """Uniformité encre — offset vs toner."""
        try:
            h, w   = img.shape[:2]
            zone   = img[:int(h*.30), :]
            gray_z = cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
            _, th  = cv2.threshold(gray_z, 80, 255, cv2.THRESH_BINARY_INV)
            if cv2.countNonZero(th) < 200: return 0.3
            hsv  = cv2.cvtColor(zone, cv2.COLOR_BGR2HSV)
            vals = hsv[:, :, 2][th > 0]
            return min(float(np.var(vals)) / 600.0, 1.0)
        except Exception: return 0.0

    @staticmethod
    def _norm(img: np.ndarray) -> np.ndarray:
        lum = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())
        if lum < 60:
            img = np.clip(img.astype(np.float32) * (120 / max(lum, 1)),
                          0, 255).astype(np.uint8)
        return img