"""
app/phases/print_detector.py — FINAL avec One-Class SVM
=========================================================
Détecte chèques imprimés : Recto (FFT+LBP+INK) + Verso (physique + One-Class SVM)

One-Class SVM :
  Entraîné sur "vrai" seulement → toute anomalie = imprimé
  Imprimés détectés : 100% | Vrais identifiés : 60%
  Utilisé comme vote d'appoint (pas décision finale)
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

    FFT_THRESHOLD = 0.45
    LBP_THRESHOLD = 0.80
    INK_THRESHOLD = 0.80

    def __init__(self):
        self.svm_pipeline = None
        self.svm_method   = None
        self.svm_img_size = (224, 224)

        # Chercher dans l'ordre : OneClass > CNN+SVM > HOG+SVM
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
                data = joblib.load(path)
                cv   = data.get("cv_mean", 0.7)
                if cv >= 0.60:
                    self.svm_pipeline = data["pipeline"]
                    self.svm_method   = method
                    self.svm_img_size = data.get("img_size", (224, 224))
                    logger.info("svm_verso_charge",
                                path=path, method=method,
                                cv_accuracy=f"{cv:.0%}")
                    break
                else:
                    logger.info("svm_verso_skip", path=path, cv=f"{cv:.0%}")
            except Exception as e:
                logger.warning("svm_erreur", path=path, error=str(e)[:80])

        if self.svm_pipeline is None:
            logger.info("svm_verso_absent",
                        note="Analyse physique seule (FFT+LBP+INK)")

        logger.info("print_detector_ready",
                    verso_svm=self.svm_pipeline is not None,
                    method=self.svm_method)

    def analyze(self, recto_bytes: bytes,
                verso_bytes: Optional[bytes] = None) -> PrintDetectionResult:

        # ── RECTO analyse physique ─────────────────────────────────
        arr   = np.frombuffer(recto_bytes, np.uint8)
        recto = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if recto is None:
            return PrintDetectionResult("UNCERTAIN", False, 0.0, {}, "illisible")

        recto  = self._norm(recto)
        fft_r  = self._fft(recto)
        lbp_r  = self._lbp(recto)
        ink_r  = self._ink(recto)

        # ── VERSO analyse physique ────────────────────────────────
        fft_v = lbp_v = 0.0
        verso_analyse = False

        if verso_bytes:
            arr_v = np.frombuffer(verso_bytes, np.uint8)
            verso = cv2.imdecode(arr_v, cv2.IMREAD_COLOR)
            if verso is not None:
                verso         = self._norm(verso)
                fft_v         = self._fft(verso)
                lbp_v         = self._lbp(verso)
                verso_analyse = True

        # Fusion recto + verso (verso = 60%)
        fft = fft_r * 0.4 + fft_v * 0.6 if verso_analyse else fft_r
        lbp = lbp_r * 0.4 + lbp_v * 0.6 if verso_analyse else lbp_r
        ink = ink_r

        # Votes physiques
        votes = sum([
            fft > self.FFT_THRESHOLD,
            lbp > self.LBP_THRESHOLD,
            ink > self.INK_THRESHOLD,
            ])

        # ── VERSO One-Class SVM ───────────────────────────────────
        svm_score = None
        svm_vote  = 0

        if self.svm_pipeline is not None and verso_bytes is not None:
            svm_score, svm_vote = self._vote_oneclass(verso_bytes)
            if svm_vote == 1:
                votes += 1
                logger.info("oneclass_vote_imprime", total_votes=votes)
            elif svm_vote == -1 and votes == 1:
                votes = 0
                logger.info("oneclass_annule_faux_positif")

        # Scores rapport
        scores = {
            "fft":              round(fft,   3),
            "lbp":              round(lbp,   3),
            "ink":              round(ink,   3),
            "fft_recto":        round(fft_r, 3),
            "lbp_recto":        round(lbp_r, 3),
            "fft_verso":        round(fft_v, 3) if verso_analyse else None,
            "lbp_verso":        round(lbp_v, 3) if verso_analyse else None,
            "oneclass_score":   round(svm_score, 3) if svm_score else None,
            "verso_disponible": verso_analyse,
            "svm_methode":      self.svm_method,
        }

        # Décision finale
        if votes >= 2:
            d, p, c = "PRINTED", True, (fft+lbp+ink)/3
            msg = ("Chèque imprimé — fft={:.2f} lbp={:.2f} ink={:.2f}{}").format(
                fft, lbp, ink,
                f" oneclass={svm_score:.2f}" if svm_score else "")
        elif votes == 1:
            d, p, c = "UNCERTAIN", False, 0.4
            msg = "Signal ambigu — vérification manuelle"
        else:
            d, p, c = "AUTHENTIC", False, 1.0-(fft+lbp+ink)/3
            msg = "Papier fiduciaire bancaire authentique"

        logger.info("print_detection",
                    decision=d, votes=votes,
                    fft=round(fft,3), lbp=round(lbp,3), ink=round(ink,3),
                    verso=verso_analyse, svm=self.svm_method)

        return PrintDetectionResult(d, p, round(c,3), scores, msg)

    def _vote_oneclass(self, verso_bytes: bytes):
        """
        One-Class SVM vote.
        pred=+1 (normal=vrai) | pred=-1 (anomalie=imprimé)

        Seuil assoupli :
          score_dec < -0.5  = anomalie très certaine → vote IMPRIMÉ
          score_dec >  0.3  = normal certain          → vote AUTHENTIQUE
          entre les deux    = neutre
        """
        try:
            import tensorflow as tf
            arr = np.frombuffer(verso_bytes, np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None: return None, 0

            # Features CNN gelé
            img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_res  = cv2.resize(img_rgb, (224, 224)).astype(np.float32)
            img_norm = (img_res / 127.5) - 1.0
            batch    = np.expand_dims(img_norm, 0)

            base = tf.keras.applications.MobileNetV2(
                input_shape=(224,224,3), include_top=False, weights="imagenet")
            base.trainable = False
            extr = tf.keras.Sequential([
                base, tf.keras.layers.GlobalAveragePooling2D()])
            feat = extr.predict(batch, verbose=0)
            features = feat.reshape(1, -1).astype(np.float32)

            pred      = self.svm_pipeline.predict(features)[0]
            score_dec = float(self.svm_pipeline.decision_function(features)[0])
            score_auth = float(1 / (1 + np.exp(-score_dec)))  # sigmoid

            logger.info("oneclass_svm",
                        pred=int(pred),
                        score_dec=round(score_dec, 3),
                        decision="VRAI" if pred == 1 else "ANOMALIE_IMPRIME")

            # Seuil assoupli (moins strict que nu seul)
            if pred == -1 and score_dec < -0.5:    # anomalie certaine
                return score_auth, 1               # vote IMPRIMÉ
            elif pred == 1 and score_dec > 0.3:    # normal certain
                return score_auth, -1              # vote AUTHENTIQUE
            return score_auth, 0                   # neutre

        except Exception as e:
            logger.warning("oneclass_erreur", error=str(e)[:100])
            return None, 0

    # ── Méthodes physiques (identiques) ───────────────────────────

    def _fft(self, img):
        try:
            gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w  = gray.shape
            zone  = gray[int(h*.1):int(h*.5), int(w*.1):int(w*.9)]
            zone  = cv2.resize(zone, (256,256))
            mag   = np.log1p(np.abs(np.fft.fftshift(
                np.fft.fft2(zone.astype(np.float32)))))
            mask  = np.ones_like(mag)
            cv2.circle(mask,(128,128),25,0,-1)
            mhf   = mag * mask
            vals  = mhf[mhf > 0]
            if vals.size == 0: return 0.0
            return min(float(np.sum(mhf > vals.mean()+2.5*vals.std()))/80.0, 1.0)
        except Exception: return 0.0

    def _lbp(self, img):
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape
            zones = [gray[int(h*.15):int(h*.35), int(w*.05):int(w*.45)],
                     gray[int(h*.15):int(h*.35), int(w*.55):int(w*.95)]]
            ents = []
            for z in zones:
                if z.size < 100: continue
                lbp_img = np.zeros_like(z)
                for i, ang in enumerate([2*np.pi*k/8 for k in range(8)]):
                    xo,yo = int(round(np.cos(ang))), int(round(-np.sin(ang)))
                    x1,y1 = max(0,-xo), max(0,-yo)
                    x2,y2 = min(w,w-xo), min(h,h-yo)
                    if y2-y1>0 and x2-x1>0:
                        nb,ct = z[y1+yo:y2+yo,x1+xo:x2+xo], z[y1:y2,x1:x2]
                        if nb.shape==ct.shape:
                            lbp_img[y1:y2,x1:x2] += (nb>=ct).astype(np.uint8)*(2**i)
                hst = np.bincount(lbp_img.flatten(),minlength=256).astype(float)
                hst /= hst.sum()+1e-9
                ents.append(-np.sum(hst[hst>0]*np.log2(hst[hst>0])))
            if not ents: return 0.5
            return min(max(1.0-(np.mean(ents)-3.0)/4.0,0.0),1.0)
        except Exception: return 0.0

    def _ink(self, img):
        try:
            h,w   = img.shape[:2]
            zone  = img[:int(h*.30),:]
            gray_z= cv2.cvtColor(zone, cv2.COLOR_BGR2GRAY)
            _,th  = cv2.threshold(gray_z,80,255,cv2.THRESH_BINARY_INV)
            if cv2.countNonZero(th)<200: return 0.3
            vals  = cv2.cvtColor(zone,cv2.COLOR_BGR2HSV)[:,:,2][th>0]
            return min(float(np.var(vals))/600.0,1.0)
        except Exception: return 0.0

    @staticmethod
    def _norm(img):
        lum = float(cv2.cvtColor(img,cv2.COLOR_BGR2GRAY).mean())
        if lum < 60:
            img = np.clip(img.astype(np.float32)*(120/max(lum,1)),0,255).astype(np.uint8)
        return img