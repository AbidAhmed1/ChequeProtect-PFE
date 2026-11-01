import cv2
import numpy as np
import os
from pathlib import Path

# =================================================================
# CONFIGURATION DES ZONES (COORDONNÉES RELATIVES % DE L'IMAGE)
# Format : (x_min, y_min, x_max, y_max)
# Ajuster ces valeurs pour caler les zones sur vos chèques.
# =================================================================
# =================================================================
# CONFIGURATION DES ZONES (Y_min, Y_max, X_min, X_max) en %
# Calibré sur le chèque Al Baraka Tunisie
# =================================================================
DEFAULT_ZONES = {
    "num_cheque":       (0.01, 0.12,  0.10, 0.35),
    "banque":           (0.02, 0.15,  0.40, 0.70),
    "montant_chiffres": (0.05, 0.25,  0.70, 0.98),
    "montant_lettres":  (0.35, 0.50,  0.08, 0.90),
    "beneficiaire":     (0.48, 0.60,  0.28, 0.85),  # X_min=0.28 : coupe "A l'ordre de"
    "titulaire":        (0.55, 0.70,  0.35, 0.70),  # Ajusté sur "KHALED TRABELSI"
    "rib":              (0.58, 0.72,  0.35, 0.80),  # Remonté pour éviter la date
    "date_lieu":        (0.75, 0.88,  0.48, 0.95),
    "signature":        (0.60, 0.85,  0.75, 0.98),
    "zone_cmc7":        (0.88, 1.00,  0.05, 0.95),  # Plus bas, les chiffres magnétiques uniquement
    "agence":           (0.55, 0.85,  0.10, 0.35)
}

class ZonalCropper:
    """
    Utilitaire pour découper un chèque en zones sémantiques.
    Format calibré : (Y_min, Y_max, X_min, X_max)
    """
    
    def __init__(self, zones_config=None):
        self.zones = zones_config or DEFAULT_ZONES

    def crop(self, image_np, zone_name):
        """Découpe une zone spécifique d'une image numpy."""
        if zone_name not in self.zones:
            return None
            
        h, w = image_np.shape[:2]
        y1_p, y2_p, x1_p, x2_p = self.zones[zone_name]
        
        # Conversion en pixels
        y1, y2 = int(y1_p * h), int(y2_p * h)
        x1, x2 = int(x1_p * w), int(x2_p * w)
        
        # Sécurité pour rester dans l'image
        y1, y2 = max(0, y1), min(h, y2)
        x1, x2 = max(0, x1), min(w, x2)
        
        if y2 <= y1 or x2 <= x1: return None
        
        return image_np[y1:y2, x1:x2]

    def get_all_crops(self, image_np):
        """Retourne un dictionnaire contenant les 6 zones découpées."""
        results = {}
        for zone in self.zones.keys():
            crop_img = self.crop(image_np, zone)
            if crop_img is not None:
                results[zone] = crop_img
        return results
