"""
app/phases/qr_validator.py
===========================
Detecteur QR code pecc.tn (plateforme TuniCheque Tunisie).

FORMAT QR pecc.tn :
  pecc.tn/TYPE/NUM_CHEQUE/RIB/IND/NOM/MONTANT_MILLIMES/DATE/SERIE
  Separateur : /
  Exemple :
    pecc.tn/1/4122752/05207000077307812272/1/MR.DOGGUI MOKHTAR/000000005000000/19092025/5005280705821737

6 PASSES SUCCESSIVES :
  Passe 1 : image couleur originale
  Passe 2 : niveaux de gris
  Passe 3 : CLAHE (contraste ameliore)
  Passe 4 : agrandie x2 (QR trop petit)
  Passe 5 : agrandie x3 (necessaire pour pecc.tn — confirme par tests)
  Passe 6 : seuillage Otsu x3 (QR sur fond sombre)
"""

import cv2
import numpy as np
import logging
from dataclasses import dataclass

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    logger = logging.getLogger(__name__)


@dataclass
class QRResult:
    found:      bool
    data:       str
    confidence: str
    position:   list
    message:    str


class QRValidator:
    """
    Detecteur QR code pecc.tn.
    Instancier une seule fois dans main.py.
    """

    MIN_QR_SIZE = 20

    def __init__(self):
        self.detector = cv2.QRCodeDetector()
        logger.info("qr_validator_ready",
                    rule="Cheque valide = QR pecc.tn present (depuis 2025)")

    def check(self, image_bytes: bytes) -> QRResult:
        """
        Detecter le QR pecc.tn en 6 passes.
        """
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)

        if img is None:
            return QRResult(False, "", "NONE", [],
                            "Image non decodable")

        h, w     = img.shape[:2]
        gray     = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        clahe    = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Passe 1 : originale
        r = self._detect(img, "originale")
        if r.found:
            return r

        # Passe 2 : gris
        r = self._detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR), "gris")
        if r.found:
            return r

        # Passe 3 : CLAHE
        r = self._detect(cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR), "clahe")
        if r.found:
            return r

        # Passe 4 : x2
        img_x2 = cv2.resize(img, (w * 2, h * 2),
                            interpolation=cv2.INTER_CUBIC)
        r = self._detect(img_x2, "x2")
        if r.found:
            return r

        # Passe 5 : x3 (confirme necessaire pour pecc.tn)
        img_x3 = cv2.resize(img, (w * 3, h * 3),
                            interpolation=cv2.INTER_CUBIC)
        r = self._detect(img_x3, "x3")
        if r.found:
            return r

        # Passe 6 : Otsu x3 (scans sombres N&B)
        _, thresh = cv2.threshold(gray, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        thresh_x3 = cv2.resize(
            cv2.cvtColor(thresh, cv2.COLOR_GRAY2BGR),
            (w * 3, h * 3), interpolation=cv2.INTER_CUBIC)
        r = self._detect(thresh_x3, "otsu_x3")
        if r.found:
            return r

        logger.warning("qr_non_detecte_6_passes",
                       dim="{}x{}".format(w, h))
        return QRResult(
            False, "", "NONE", [],
            "Aucun QR pecc.tn detecte — cheque invalide (anterieur a 2025)"
        )

    def _detect(self, img_color: np.ndarray,
                passe_nom: str) -> QRResult:
        """Tentative de detection sur une version de l image."""
        try:
            data, points, _ = self.detector.detectAndDecode(img_color)
        except Exception as e:
            return QRResult(False, "", "NONE", [],
                            "Erreur passe {}: {}".format(passe_nom, e))

        if points is not None and len(points) > 0:
            pts  = points[0]
            w_qr = float(np.linalg.norm(pts[0] - pts[1]))
            h_qr = float(np.linalg.norm(pts[1] - pts[2]))
            size = (w_qr + h_qr) / 2

            if size < self.MIN_QR_SIZE:
                return QRResult(False, "", "LOW", [],
                                "QR trop petit ({:.0f}px)".format(size))

            pos = pts.tolist() if hasattr(pts, "tolist") else []

            if not data:
                logger.info("qr_detected_not_readable",
                            passe=passe_nom, size=round(size))
                return QRResult(
                    True,
                    "(QR detecte — contenu non lisible)",
                    "LOW", pos,
                    "QR present visuellement mais non decodable"
                )

            logger.info("qr_decoded",
                        passe=passe_nom,
                        size=round(size),
                        debut=data[:40])
            # Accepter https://pecc.tn/ ET pecc.tn/
            if "pecc.tn" not in data.lower():
                return QRResult(False, data, "LOW", pos,
                                "QR detecte mais pas pecc.tn")
            return QRResult(
                True, data, "HIGH", pos,
                "QR pecc.tn present — passe {}, taille {:.0f}px".format(
                    passe_nom, size)
            )

        return QRResult(False, "", "NONE", [],
                        "Passe {} : aucun QR".format(passe_nom))