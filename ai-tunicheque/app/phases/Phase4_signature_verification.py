"""
Phase 4 - Verification de signature par reseau siamois + YOLO.

Flux :
  1. Extraire la region signature via YOLO (fallback sur zone fixe)
  2. Preprocesser : GRAY -> CLAHE -> Binarisation OTSU (N&B) -> Dilation 2x2 -> Morph Cleanup -> 105x105
  3. Générer l'embedding (vecteur) via la couche pénultième du réseau siamois
  4. Charger les specimens du tireur (fichiers locaux par RIB ou PostgreSQL)
  5. Comparer par Similarité Cosine (embedding vs chaque specimen)
  6. Retourner le meilleur score (MAX) et la décision à 3 niveaux

Décision (3 niveaux, standard bancaire) :
  score >= THRESHOLD_MATCH  (0.80) -> MATCH      ✅  Validation automatique
  score >= THRESHOLD_REVIEW (0.50) -> REVIEW     ⚠️  Envoi expert humain
  score <  THRESHOLD_REVIEW (0.50) -> NO_MATCH   ❌  Rejet automatique

Optimisation :
  Les embeddings des spécimens sont mis en cache (dict mémoire) pour éviter
  de repasser les images dans le réseau à chaque vérification.
  La comparaison s'effectue par Similarité Cosine (plus robuste qu'euclidienne
  pour capturer le "style" d'une signature indépendamment de la magnitude).

Note sur la Dilation :
  Kernel intentionnellement minimal (2x2, 1 itération) pour éviter de fusionner
  des traits fins cruciaux à la distinction authentique/imitation.
"""

import numpy as np
import cv2
import os
import time
import re
import tensorflow as tf
from pathlib import Path
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import structlog
from ultralytics import YOLO

from app.models.pipeline_models import PhaseResult

load_dotenv()
logger = structlog.get_logger()


@tf.keras.utils.register_keras_serializable()
class DistanceLayer(tf.keras.layers.Layer):
    """Custom layer to compute absolute difference between two feature vectors."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def call(self, inputs):
        return tf.abs(inputs[0] - inputs[1])


class SiameseSignaturePhase:
    """
    Verificateur de signature par reseau siamois (SigNet).
    - YOLOv8      : détourage précis de la zone signature
    - Embedding   : vecteur extrait de la couche pénultième (mis en cache)
    - Cosine Sim  : comparaison robuste au style, insensible à la magnitude
    - Décision    : 3 niveaux (MATCH / REVIEW / NO_MATCH)
    """

    # Dossier de base (backend/service-ai)
    BASE_DIR = Path(__file__).resolve().parent.parent.parent

    # Chemin vers le modele de l'encodeur (produit les embeddings)
    MODEL_PATH = BASE_DIR / "saved_models" / "signature_encoder.keras"

    # Chemin vers le modele YOLO de detection
    YOLO_MODEL_PATH = BASE_DIR / "saved_models" / "best.pt"

    # Dossier de reference bancaire locale (nom_fichier = RIB.png / RIB.jpg)
    REF_DIR = BASE_DIR / "database_signatures"

    # Dossiers d'entrainement acceptes (fallback de recherche par nom ou RIB)
    TRAINING_DATA_DIRS = [
        BASE_DIR / "training" / "Augmented",
        BASE_DIR / "training" / "signatures",
        BASE_DIR / "training",
        BASE_DIR.parent.parent / "training_data" / "Augmented",
        BASE_DIR / "training_data" / "Augmented",
        BASE_DIR / "training_data",
        BASE_DIR / "app" / "sig_nom",
    ]

    # Taille standard SigNet
    IMG_SIZE = (105, 105)

    # ── Seuils de décision (standard bancaire) ──────────────────────────────
    # >= THRESHOLD_MATCH  -> MATCH    ✅ validation automatique
    # >= THRESHOLD_REVIEW -> REVIEW   ⚠️ renvoi expert
    # <  THRESHOLD_REVIEW -> NO_MATCH ❌ rejet automatique
    THRESHOLD_MATCH  = 0.80
    THRESHOLD_REVIEW = 0.50

    # Zone signature de secours en fractions de l'image (bas-droite)
    SIG_REGION = (0.60, 0.85, 0.75, 0.98)

    def __init__(self):
        """Chargement des modeles et init du cache d'embeddings."""
        self.model    = self._load_model()
        self._encoder = self._build_encoder()   # Sous-réseau pour les embeddings
        self.yolo     = self._load_yolo()
        self.db       = create_engine(
            os.getenv("DATABASE_URL",
                      "postgresql://cheque_admin:ChequeAdmin2025!@localhost:5433/cheque_db")
        )
        # Cache des embeddings de specimens {chemin_fichier: vecteur_numpy}
        self._embedding_cache: dict[str, np.ndarray] = {}

        logger.info(
            "phase4_initialized",
            siamese_loaded  = self.model is not None,
            encoder_built   = self._encoder is not None,
            yolo_loaded     = self.yolo is not None,
            threshold_match = self.THRESHOLD_MATCH,
            threshold_review= self.THRESHOLD_REVIEW,
        )

    # ── Chargement des modèles ──────────────────────────────────────────────

    def _load_yolo(self):
        """Charge le modele YOLO pour la detection de la zone signature."""
        if not self.YOLO_MODEL_PATH.exists():
            logger.warning("yolo_signature_model_not_found", path=str(self.YOLO_MODEL_PATH))
            return None
        try:
            return YOLO(str(self.YOLO_MODEL_PATH))
        except Exception as e:
            logger.error("yolo_load_failed", error=str(e))
            return None

    def _load_model(self):
        """Charge le réseau siamois complet depuis le disque."""
        if not self.MODEL_PATH.exists():
            logger.warning("siamese_model_not_found", expected=str(self.MODEL_PATH))
            return None
        try:
            # L'encodeur ne contient pas de custom loss, il produit juste des embeddings
            model = tf.keras.models.load_model(str(self.MODEL_PATH), compile=False, safe_mode=False)
            logger.info("signature_encoder_loaded")
            return model
        except Exception as e:
            logger.error("model_load_failed", error=str(e))
            return None

    def _build_encoder(self):
        """
        Dans cette version, self.model EST déjà l'encodeur autonome.
        """
        return self.model

    # ── Prétraitement ───────────────────────────────────────────────────────

    def extract_sig_region(self, image_bytes: bytes) -> np.ndarray | None:
        """Extrait la zone signature via YOLO (fallback sur zone fixe bas-droite)."""
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]

        # 1. Tentative YOLO (classe 5 = signature dans notre modele best.pt)
        if self.yolo:
            results = self.yolo.predict(img, conf=0.25, verbose=False)
            for r in results:
                for box in r.boxes:
                    if int(box.cls[0]) == 5:  # 'signature'
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                        # Marge de 5% pour ne pas couper les traits de bord
                        pad_h = int((y2 - y1) * 0.05)
                        pad_w = int((x2 - x1) * 0.05)
                        ry1, ry2 = max(0, int(y1) - pad_h), min(h, int(y2) + pad_h)
                        rx1, rx2 = max(0, int(x1) - pad_w), min(w, int(x2) + pad_w)
                        logger.info("yolo_sig_region_detected", y1=ry1, y2=ry2, x1=rx1, x2=rx2)
                        return img[ry1:ry2, rx1:rx2]

        # 2. Fallback zone fixe (bas-droite du cheque)
        # Attention : sur certains chèques d'entreprise, la zone peut être décalée
        # par des tampons. Surveiller via les debug_crops si le fallback est utilisé.
        logger.warning("sig_extraction_fallback_zonal")
        y1f, y2f, x1f, x2f = self.SIG_REGION
        region = img[int(y1f * h):int(y2f * h), int(x1f * w):int(x2f * w)]
        return region if region.size > 0 else None

    def preprocess_sig(self, sig_img: np.ndarray) -> np.ndarray | None:
        """
        Pipeline de prétraitement robuste pour la vérification de signature :
          GRAY -> CLAHE -> OTSU (inversé) -> Dilation 2x2 (minimal!) -> Morph Open -> 105x105

        Note sur la dilation :
          Kernel (2,2), 1 itération seulement. Un kernel plus grand risquerait de
          fusionner des traits fins cruciaux pour distinguer une signature authentique
          d'une imitation lente et hésitante.
        """
        if sig_img is None:
            return None

        # BGR -> Niveaux de gris
        gray = cv2.cvtColor(sig_img, cv2.COLOR_BGR2GRAY)

        # Amélioration du contraste (CLAHE) — essentiel pour les chèques colorés
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray = clahe.apply(gray)

        # Binarisation OTSU inversée (encre noire sur fond blanc)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

        # Renforcement des traits (Thickening) — pour les stylos fins
        # MINIMAL : kernel 2x2, 1 itération uniquement
        kernel_dil = np.ones((2, 2), np.uint8)
        binary = cv2.dilate(binary, kernel_dil, iterations=1)

        # Suppression du bruit résiduel
        kernel_open = np.ones((2, 2), np.uint8)
        cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

        # Redimensionnement SigNet 105x105 + normalisation [0,1]
        resized = cv2.resize(cleaned, self.IMG_SIZE)
        return (resized.astype("float32") / 255.0)[..., np.newaxis]

    # ── Embeddings & Similarité ─────────────────────────────────────────────

    def _get_embedding(self, processed_img: np.ndarray) -> np.ndarray | None:
        """
        Génère un vecteur d'embedding pour une signature prétraitée.
        Utilise le sous-réseau encodeur (couche pénultième).
        """
        if self._encoder is None or processed_img is None:
            return None
        img_batch = np.expand_dims(processed_img, axis=0)  # (1, 105, 105, 1)
        embedding = self._encoder.predict(img_batch, verbose=0)
        return embedding[0]  # vecteur 1D (N,)

    def _cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        """
        Calcule la Similarité Cosine entre deux vecteurs d'embedding.
        Plage : [0.0, 1.0] — plus proche de 1.0 = plus similaire.

        Avantage vs Distance Euclidienne :
          La cosine mesure l'ORIENTATION des vecteurs (le "style" de la signature)
          et non leur magnitude. Plus robuste face aux variations de pression du stylo.
        """
        norm_a = np.linalg.norm(vec_a)
        norm_b = np.linalg.norm(vec_b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))

    def _get_specimen_embedding(self, spec_path: str) -> np.ndarray | None:
        """
        Récupère l'embedding d'un spécimen avec mise en cache.
        Le vecteur est calculé une seule fois et réutilisé pour toutes les
        vérifications ultérieures du même spécimen.
        """
        # Cache hit
        if spec_path in self._embedding_cache:
            return self._embedding_cache[spec_path]

        # Cache miss : calculer et mettre en cache
        spec_img = cv2.imread(spec_path)
        if spec_img is None:
            logger.warning("specimen_unreadable", path=spec_path)
            return None

        processed = self.preprocess_sig(spec_img)
        embedding  = self._get_embedding(processed)

        if embedding is not None:
            self._embedding_cache[spec_path] = embedding
            logger.info("embedding_cached", path=spec_path, dim=embedding.shape[0])

        return embedding

    def _predict_raw(self, sig_processed: np.ndarray, spec_processed: np.ndarray) -> float:
        """
        Prédiction directe via le modèle siamois complet (sans embedding).
        Utilisé comme fallback si l'encodeur n'a pas pu être extrait.
        """
        a = np.expand_dims(sig_processed, axis=0)
        b = np.expand_dims(spec_processed, axis=0)
        raw = self.model.predict([a, b], verbose=0)
        return float(raw[0][0])

    # ── Récupération des spécimens ──────────────────────────────────────────

    def get_reference_from_file(self, rib: str) -> str | None:
        """Trouve une signature de référence locale par RIB (recherche flexible)."""
        if not rib:
            return None

        rib_clean = re.sub(r"[^0-9]", "", str(rib))

        # Recherche exacte (.png / .jpg)
        for ext in [".png", ".jpg", ".jpeg"]:
            exact = self.REF_DIR / f"{rib_clean}{ext}"
            if exact.exists():
                return str(exact)

        # Recherche par sous-chaîne (tolérance aux erreurs OCR sur le RIB)
        if self.REF_DIR.exists():
            for f in self.REF_DIR.iterdir():
                if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                    filename_clean = re.sub(r"[^0-9]", "", f.stem)
                    if not filename_clean:
                        continue
                    if filename_clean in rib_clean or rib_clean in filename_clean:
                        logger.info("fuzzy_rib_match_found", file=f.name, rib=rib_clean)
                        return str(f)

        return None

    def get_specimens(self, cheque_id: str, rib: str = None, name: str = None) -> list[str]:
        """
        Récupère TOUS les spécimens disponibles pour un RIB/nom/cheque_id.
        Sources (par priorité) :
          1. Fichiers locaux (database_signatures/) — par RIB
          2. Dossier training_data/ — par NOM ou RIB
          3. PostgreSQL (table specimens_signatures) — par identifiant chèque
        """
        all_paths = []

        # 1. Priorité : référence locale par RIB dans database_signatures/
        ref_path = self.get_reference_from_file(rib)
        if ref_path:
            logger.info("reference_found_in_bank_local_db", rib=rib, path=ref_path)
            all_paths.append(ref_path)

        # 2. Recherche dans training_data/ par nom ou RIB
        search_terms = []
        if name: search_terms.append(name.upper())
        if rib: search_terms.append(re.sub(r"[^0-9]", "", str(rib)))

        for training_dir in self.TRAINING_DATA_DIRS:
            if not training_dir.exists():
                continue

            for term in search_terms:
                # Chercher un dossier dont le nom contient le terme
                for folder in training_dir.iterdir():
                    if folder.is_dir() and term in folder.name.upper():
                        logger.info(
                            "specimens_found_in_training_data",
                            source=folder.name,
                            term=term,
                            training_dir=str(training_dir)
                        )
                        for f in folder.iterdir():
                            if f.is_file() and f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                                all_paths.append(str(f))

        # 3. Fallback : PostgreSQL — requête directe par RIB (sans JOIN cheques)
        rib_clean_db = re.sub(r"[^0-9]", "", str(rib)) if rib else None
        if rib_clean_db:
            try:
                with self.db.connect() as conn:
                    rows = conn.execute(text("""
                        SELECT image_path
                        FROM specimens_signatures
                        WHERE rib = :rib
                          AND is_active = TRUE
                        ORDER BY created_at DESC
                        LIMIT 5
                    """), {"rib": rib_clean_db}).fetchall()
                    db_paths = [r[0] for r in rows if r[0] and Path(r[0]).exists()]
                    if db_paths:
                        logger.info("specimens_found_in_db", rib=rib_clean_db, count=len(db_paths))
                    all_paths.extend(db_paths)
            except Exception as e:
                logger.error("get_specimens_db_failed", error=repr(e))

        # Suppression des doublons (ordre préservé)
        return list(dict.fromkeys(all_paths))

    # ── Décision à 3 niveaux ────────────────────────────────────────────────

    @staticmethod
    def _decision(score: float, threshold_match: float, threshold_review: float) -> str:
        """
        Standard bancaire à 3 niveaux :
          MATCH    -> validation automatique ✅
          REVIEW   -> renvoi expert humain   ⚠️
          NO_MATCH -> rejet automatique      ❌
        """
        if score >= threshold_match:
            return "MATCH"
        elif score >= threshold_review:
            return "REVIEW"
        else:
            return "NO_MATCH"

    # ── Point d'entrée principal ────────────────────────────────────────────

    async def verify(self, recto_bytes: bytes, cheque_id: str, rib: str = None, 
                     name: str = None, strict_mode: bool = False, manual_specimens: list[str] = None) -> PhaseResult:
        """
        Vérification complète de la signature.

        Paramètres :
          recto_bytes : image brute du recto du chèque
          cheque_id   : identifiant chèque (pour requête PostgreSQL)
          rib         : RIB extrait par Phase 3
          name        : Nom du tireur (si disponible pour recherche training_data)
          strict_mode : si True, durcit les seuils (+0.10)
          manual_specimens : liste de chemins vers des spécimens forcés
        """
        t0 = time.time()

        # Appliquer les seuils selon le mode
        th_match  = self.THRESHOLD_MATCH  + (0.10 if strict_mode else 0.0)
        th_review = self.THRESHOLD_REVIEW + (0.05 if strict_mode else 0.0)

        # ── 1. Extraction zone signature ────────────────────────────────────
        region = self.extract_sig_region(recto_bytes)
        if region is None:
            return PhaseResult(
                phase="signature", score=0.0, passed=False,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "error": "region_vide",
                    "decision": "NO_MATCH",
                    "verified": False,
                    "verification_status": "region_missing",
                }
            )

        # ── 1b. Détecter signature vide (zone blanche sans encre) ───────────
        # Si la zone signature ne contient pas assez de pixels d'encre (< 2% de
        # pixels sombres après seuillage), c'est une case vide → refus immédiat.
        gray_check = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        _, bin_check = cv2.threshold(gray_check, 0, 255,
                                     cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_ratio = float(np.count_nonzero(bin_check)) / max(bin_check.size, 1)
        if ink_ratio < 0.02:
            logger.warning("signature_vide_detectee", ink_ratio=round(ink_ratio, 4))
            return PhaseResult(
                phase="signature", score=0.0, passed=False,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "decision": "NO_MATCH",
                    "verified": False,
                    "verification_status": "signature_vide",
                    "note": "Zone signature vide — aucune encre détectée",
                    "ink_ratio": round(ink_ratio, 4),
                }
            )

        # ── 2. Fallback si modèle absent ────────────────────────────────────
        if self.model is None:
            logger.warning("siamese_model_absent_fallback")
            return PhaseResult(
                phase="signature", score=0.5, passed=True,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "note": "modele_absent",
                    "decision": "REVIEW",
                    "verified": False,
                    "verification_status": "model_missing",
                }
            )

        # ── 3. Prétraitement de la signature du chèque ──────────────────────
        sig_processed = self.preprocess_sig(region)
        sig_embedding = self._get_embedding(sig_processed)

        # ── 4. Récupération des spécimens ────────────────────────────────────
        specimen_paths = manual_specimens or []
        
        # Si pas assez de spécimens manuels, on cherche en DB/Local/Training
        if not specimen_paths:
            try:
                db_specs = self.get_specimens(cheque_id, rib, name)
                if db_specs:
                    specimen_paths.extend(db_specs)
            except Exception as e:
                logger.error("get_specimens_failed", error=str(e))
        
        if not specimen_paths:
            logger.warning("no_specimens_found", cheque_id=cheque_id, rib=rib, name=name)
            return PhaseResult(
                phase="signature", score=0.5, passed=True,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "note": "pas_de_specimen",
                    "decision": "REVIEW",
                    "verified": False,
                    "verification_status": "specimens_missing",
                }
            )

        # ── 5. Comparaison avec TOUS les spécimens (Score MAX) ───────────────
        scores, errors = [], []
        for spec_path in specimen_paths:
            try:
                score = 0.0

                if sig_embedding is not None and self._encoder is not None:
                    # Chemin rapide : comparaison par embeddings (Cosine Similarity)
                    spec_embedding = self._get_specimen_embedding(spec_path)
                    if spec_embedding is not None:
                        score = self._cosine_similarity(sig_embedding, spec_embedding)

                else:
                    # Fallback : réseau siamois complet (plus lent)
                    spec_img = cv2.imread(spec_path)
                    if spec_img is None:
                        continue
                    spec_processed = self.preprocess_sig(spec_img)
                    score = self._predict_raw(sig_processed, spec_processed)

                    # Debug : comparaison visuelle côte-à-côte
                    vis_spec = (spec_processed.reshape(self.IMG_SIZE) * 255).astype(np.uint8)
                    vis_sig  = (sig_processed.reshape(self.IMG_SIZE)  * 255).astype(np.uint8)
                    comparison = np.hstack([vis_spec, vis_sig])
                    os.makedirs("tmp", exist_ok=True)
                    cv2.imwrite(f"tmp/debug_compare_{len(scores)}.jpg", comparison)

                scores.append(round(score, 4))
                logger.info(
                    "specimen_compared",
                    spec=Path(spec_path).name,
                    score=round(score, 4),
                    rib=rib,
                    mode="cosine" if (sig_embedding is not None and self._encoder is not None) else "siamese_full"
                )

            except Exception as e:
                errors.append(str(e))
                logger.error("specimen_comparison_failed", path=spec_path, error=str(e))

        if not scores:
            return PhaseResult(
                phase="signature", score=0.0, passed=False,
                duration_ms=int((time.time() - t0) * 1000),
                details={
                    "error": "tous_specimens_illisibles",
                    "errors": errors,
                    "decision": "NO_MATCH",
                    "verified": False,
                    "verification_status": "comparison_failed",
                }
            )

        # ── 6. Décision sur le score MAX (score si ressemble à AU MOINS un spécimen) ──
        best_score = max(scores)
        decision   = self._decision(best_score, th_match, th_review)
        is_passed  = decision in ("MATCH", "REVIEW")   # REVIEW passe pour ne pas bloquer

        logger.info(
            "phase4_decision",
            rib=rib, best_score=best_score, all_scores=scores,
            decision=decision, strict_mode=strict_mode,
            specimens_count=len(scores)
        )

        return PhaseResult(
            phase="signature",
            score=round(best_score, 4),
            passed=is_passed,
            duration_ms=int((time.time() - t0) * 1000),
            details={
                "decision":         decision,
                "best_score":       round(best_score, 4),
                "all_scores":       scores,
                "specimens_count":  len(scores),
                "threshold_match":  th_match,
                "threshold_review": th_review,
                "strict_mode":      strict_mode,
                "verified":         True,
                "verification_status": "verified",
                "errors":           errors if errors else None,
            }
        )
