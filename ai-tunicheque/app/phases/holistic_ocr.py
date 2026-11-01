"""
holistic_ocr.py
===============
Module de Reconnaissance Holistique (mot par mot) des montants manuscrits
sur les chèques bancaires tunisiens.

Auteur  : PFE Chèque Tunisien
Version : 3.0 (Advanced Features)

Pipeline amélioré :
  1. Prétraitement  : Bilateral Filter + Sauvola + Deskew + Slant Correction
  2. Segmentation   : Connected Components + Regroupement adaptatif
  3. Reconnaissance : Features Hybrides (Densité 13x13 + HOG) + SVM OvO
  4. Post-traitement: Correction Lexicale avancée via thefuzz
"""

import cv2
import numpy as np
import os
import joblib
import structlog
from typing import List, Tuple, Dict, Optional
from skimage.filters import threshold_sauvola
from skimage.feature import hog
from sklearn.svm import SVC
from sklearn.preprocessing import LabelEncoder

try:
    from thefuzz import process as fuzz_process
    HAS_THEFUZZ = True
except ImportError:
    import difflib
    HAS_THEFUZZ = False

# Configuration du logging
logger = structlog.get_logger()

# =============================================================================
class ChequeHandwritingReader:
    """
    Reconnaissance holistique haute précision pour montants manuscrits.
    """

    # Lexique bancaire tunisien complet (Français)
    BANKING_DICT = [
        "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf",
        "dix", "onze", "douze", "treize", "quatorze", "quinze", "seize",
        "dix-sept", "dix-huit", "dix-neuf",
        "vingt", "trente", "quarante", "cinquante", "soixante",
        "soixante-dix", "quatre-vingt", "quatre-vingt-dix",
        "cent", "cents", "mille", "million", "milliard",
        "millions", "milliards",
        "dinar", "dinars", "millime", "millimes", "et", "seulement"
    ]

    # Caractéristiques : Densité (169) + HOG (81) = 250
    # On va ajuster HOG pour obtenir exactement 81 ou proche
    DENSITY_DIM = 169  # 13x13
    HOG_DIM = 81       # 3x3 cells, 9 orientations (3*3*9=81)

    # =========================================================================
    def __init__(self, model_path: str = None, window_size: int = 25, sauvola_k: float = 0.2):
        self.window_size = window_size
        self.sauvola_k   = sauvola_k
        self.target_size = (130, 130)

        # DISABLED: Untrained SVM unreliable for production
        self.model = None
        self.label_encoder = LabelEncoder()
        self.is_trained = False
        self._base_gap_ratio = 0.045

        logger.warning("🚫 Holistic SVM DISABLED - requires real training data")

    # =========================================================================
    # ÉTAPE 1 : PRÉTRAITEMENT AVANCÉ
    # =========================================================================

    def preprocess_field(self, image: np.ndarray) -> Optional[np.ndarray]:
        """Pipeline complet : Bilareral -> Sauvola -> Deskew -> Slant."""
        try:
            if image is None or image.size == 0: return None

            # 1. Mise à l'échelle pour uniformité
            h, w = image.shape[:2]
            if w < 300:
                scale = 300 / w
                image = cv2.resize(image, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)

            # 2. Gris + Réduction de bruit bilatérale (préserve les bords des lettres)
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image.copy()
            denoised = cv2.bilateralFilter(gray, 9, 75, 75)

            # 3. Binarisation de Sauvola (robuste aux textures de fond des chèques)
            thresh = threshold_sauvola(denoised, window_size=self.window_size, k=self.sauvola_k)
            binary = (denoised > thresh).astype(np.uint8) * 255

            # 4. Correction d'inclinaison globale (Deskew)
            binary = self._deskew(binary)

            # 5. Nettoyage morphologique léger (suppression petits points)
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel)

            return binary
        except Exception as e:
            logger.error("Pretreatment failed", error=str(e))
            return None

    def _deskew(self, binary: np.ndarray) -> np.ndarray:
        """Redressement par transformée de Hough."""
        try:
            coords = np.column_stack(np.where(binary == 0))
            angle = cv2.minAreaRect(coords)[-1]
            if angle < -45: angle = -(90 + angle)
            else: angle = -angle
            
            if abs(angle) < 0.5: return binary

            (h, w) = binary.shape[:2]
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            return cv2.warpAffine(binary, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        except: return binary

    def _correct_slant(self, word_img: np.ndarray) -> np.ndarray:
        """Correction de l'italique (Shear transformation)."""
        try:
            # On cherche l'angle de cisaillement optimal (méthode simplifiée par moments)
            img = 255 - word_img
            m = cv2.moments(img)
            if abs(m['mu02']) < 1e-2: return word_img
            
            mu11 = m['mu11']
            mu02 = m['mu02']
            rho = mu11 / mu02
            
            if abs(rho) < 0.1: return word_img
            
            # Transformation affine pour compenser le slant
            (h, w) = word_img.shape[:2]
            M = np.float32([[1, -rho, 0.5 * h * rho], [0, 1, 0]])
            return cv2.warpAffine(word_img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        except: return word_img

    # =========================================================================
    # ÉTAPE 2 : SEGMENTATION
    # =========================================================================

    def segment_into_words(self, binary_field: np.ndarray, debug_dir: str = None) -> List[np.ndarray]:
        """Segmentation par composantes connectées et regroupement horizontal."""
        if binary_field is None: return []
        
        # Inversion pour détection de contours (blanc sur noir)
        inv = cv2.bitwise_not(binary_field)
        num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
        
        # Filtrage bruit (composants minuscules)
        min_area = (binary_field.shape[0] * binary_field.shape[1]) * 0.0005
        components = []
        for i in range(1, num_labels):
            x, y, w, h, area = stats[i]
            if area > min_area:
                components.append({'x': x, 'y': y, 'w': w, 'h': h})
        
        if not components: return []
        components.sort(key=lambda c: c['x'])

        # Groupement adaptatif
        gap_thresh = max(20, int(binary_field.shape[1] * self._base_gap_ratio))
        words_boxes = []
        if components:
            curr = [components[0]]
            for i in range(1, len(components)):
                prev_right = curr[-1]['x'] + curr[-1]['w']
                dist = components[i]['x'] - prev_right
                if dist < gap_thresh: curr.append(components[i])
                else:
                    words_boxes.append(curr)
                    curr = [components[i]]
            words_boxes.append(curr)

        word_images = []
        for i, boxes in enumerate(words_boxes):
            x1 = min(b['x'] for b in boxes)
            x2 = max(b['x'] + b['w'] for b in boxes)
            y1 = min(b['y'] for b in boxes)
            y2 = max(b['y'] + b['h'] for b in boxes)
            
            crop = binary_field[max(0, y1-2):y2+2, max(0, x1-2):x2+2]
            # Appliquer Slant Correction sur chaque mot
            crop = self._correct_slant(crop)
            
            # Normaliser avec aspect ratio conservé (padding au lieu de stretch)
            norm = self._normalize_with_padding(crop, self.target_size)
            word_images.append(norm)
            
            if debug_dir:
                os.makedirs(debug_dir, exist_ok=True)
                cv2.imwrite(os.path.join(debug_dir, f"word_{i:02d}.jpg"), norm)
                
        return word_images

    def _normalize_with_padding(self, img: np.ndarray, size: Tuple[int, int]) -> np.ndarray:
        """Redimensionne en gardant les proportions et en ajoutant des marges blanches."""
        h, w = img.shape[:2]
        target_w, target_h = size
        
        scale = min(target_w / w, target_h / h) * 0.9 # 10% marge
        new_w, new_h = int(w * scale), int(h * scale)
        
        resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
        
        canvas = np.full((target_h, target_w), 255, dtype=np.uint8)
        off_x = (target_w - new_w) // 2
        off_y = (target_h - new_h) // 2
        canvas[off_y:off_y+new_h, off_x:off_x+new_w] = resized
        return canvas

    # =========================================================================
    # ÉTAPE 3 : CARACTÉRISTIQUES HYBRIDES (Densité + HOG)
    # =========================================================================

    def extract_features(self, word_img: np.ndarray) -> np.ndarray:
        """Combine Densité (13x13) et HOG (81)."""
        # 1. Densité matricielle
        inv = 255 - word_img
        density = []
        step = 10 # car 130 / 10 = 13 blocs
        for y in range(0, 130, step):
            for x in range(0, 130, step):
                block = inv[y:y+step, x:x+step]
                density.append(np.sum(block > 0) / 100.0)
        
        # 2. HOG (Histogram of Oriented Gradients)
        # On veut 81 features : 3x3 cells * 9 orientations
        hog_feats = hog(
            word_img,
            orientations=9,
            pixels_per_cell=(43, 43), # 130 / 43 ~= 3 cells
            cells_per_block=(1, 1),
            block_norm='L2-Hys',
            visualize=False
        )
        
        # S'assurer que HOG fait la bonne taille (ici 3x3x9 = 81)
        if len(hog_feats) > 81: hog_feats = hog_feats[:81]
        elif len(hog_feats) < 81: hog_feats = np.pad(hog_feats, (0, 81 - len(hog_feats)))

        return np.hstack([density, hog_feats]).astype(np.float32)

    # =========================================================================
    # ÉTAPE 4 : MODÈLE & PRÉDICTION
    # =========================================================================

    def train_dummy_model(self):
        """Initialisation pour tests."""
        logger.info("Initializing Dummy SVM Model")
        n_classes = len(self.BANKING_DICT)
        X = np.random.rand(n_classes * 10, self.DENSITY_DIM + 81).astype(np.float32)
        y = (self.BANKING_DICT * 10)
        
        self.label_encoder.fit(y)
        y_enc = self.label_encoder.transform(y)
        self.model.fit(X, y_enc)
        self.is_trained = True

    def train(self, X: np.ndarray, y: List[str], save_path: str = None):
        """Entrainement réel."""
        self.label_encoder.fit(y)
        y_enc = self.label_encoder.transform(y)
        self.model.fit(X, y_enc)
        self.is_trained = True
        if save_path: self.save_model(save_path)

    def save_model(self, path: str):
        joblib.dump({'model': self.model, 'encoder': self.label_encoder}, path)
        logger.info("Model saved", path=path)

    def _load_model(self, path: str):
        try:
            data = joblib.load(path)
            self.model = data['model']
            self.label_encoder = data['encoder']
            self.is_trained = True
            logger.info("Model loaded", path=path)
        except Exception as e:
            logger.error("Failed to load model", error=str(e))

    def predict_word(self, word_img: np.ndarray) -> Tuple[str, float]:
        """DISABLED - Untrained model returns neutral result"""
        logger.debug("Holistic predict_word DISABLED")
        return "", 0.0

    def lexical_correction(self, word: str, min_score: int = 75) -> str:
        """Correction par distance de Levenshtein (TheFuzz)."""
        if not word or word == "?": return word
        w_low = word.lower()
        if w_low in self.BANKING_DICT: return w_low
        
        if HAS_THEFUZZ:
            match, score = fuzz_process.extractOne(w_low, self.BANKING_DICT)
            return match if score >= min_score else word
        else:
            matches = difflib.get_close_matches(w_low, self.BANKING_DICT, n=1, cutoff=0.7)
            return matches[0] if matches else word

    # =========================================================================
    # PIPELINE FINAL
    # =========================================================================

    def read_cheque_amount(self, crop: np.ndarray, debug_dir: str = None) -> Dict:
        """Execute le pipeline complet sur un crop de chèque."""
        res = {'text': '', 'words': [], 'confidences': [], 'raw_words': []}
        
        # 1. Prétraitement
        binary = self.preprocess_field(crop)
        if binary is None: return res
        
        # 2. Segmentation
        word_imgs = self.segment_into_words(binary, debug_dir)
        
        # 3 & 4. Reconnaissance & Correction
        for w_img in word_imgs:
            raw, conf = self.predict_word(w_img)
            corrected = self.lexical_correction(raw)
            res['words'].append(corrected)
            res['raw_words'].append(raw)
            res['confidences'].append(round(conf, 3))
            
        res['text'] = " ".join(res['words']).upper()
        return res

if __name__ == "__main__":
    reader = ChequeHandwritingReader()
    if not reader.is_trained:
        reader.train_dummy_model()
    # Test avec une image vide
    dummy = np.full((100, 600, 3), 255, dtype=np.uint8)
    print(reader.read_cheque_amount(dummy))
