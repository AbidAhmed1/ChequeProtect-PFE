"""
crop_signature.py — Crop automatique de la zone signature via YOLO
Usage :
  python crop_signature.py <image> <rib>

Exemples :
  python crop_signature.py Chequetest/chequeR.jpg  20003030001148336517
  python crop_signature.py Chequetest/ChequeT.jpg  08010011042000192
  python crop_signature.py Chequetest/recto.jpg    07152781829876246775
"""

import sys
import cv2
import numpy as np
from pathlib import Path
from ultralytics import YOLO

YOLO_PATH  = Path("saved_models/best.pt")
OUTPUT_DIR = Path("database_signatures")
SIG_CLASS  = 5
CONF       = 0.25
FALLBACK   = (0.60, 0.85, 0.75, 0.98)  # y1, y2, x1, x2 en fractions


def crop_and_save(image_path: str, rib: str):
    img_path  = Path(image_path)
    rib_clean = rib.replace(" ", "").replace("-", "")

    if not img_path.exists():
        print(f"❌ Image introuvable : {image_path}")
        return

    img = cv2.imread(str(img_path))
    if img is None:
        print(f"❌ Impossible de lire l'image : {image_path}")
        return

    h, w  = img.shape[:2]
    region = None

    # 1. YOLO
    if YOLO_PATH.exists():
        model   = YOLO(str(YOLO_PATH))
        results = model.predict(img, conf=CONF, verbose=False)
        for r in results:
            for box in r.boxes:
                if int(box.cls[0]) == SIG_CLASS:
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                    pad_h = int((y2 - y1) * 0.05)
                    pad_w = int((x2 - x1) * 0.05)
                    region = img[max(0, y1-pad_h):min(h, y2+pad_h),
                                 max(0, x1-pad_w):min(w, x2+pad_w)]
                    print(f"✅ YOLO : zone signature détectée [{x1},{y1} → {x2},{y2}]")
                    break
            if region is not None:
                break
    else:
        print(f"⚠️  Modèle YOLO introuvable ({YOLO_PATH}) — fallback zone fixe")

    # 2. Fallback zone fixe bas-droite
    if region is None or region.size == 0:
        y1f, y2f, x1f, x2f = FALLBACK
        region = img[int(y1f*h):int(y2f*h), int(x1f*w):int(x2f*w)]
        print("⚠️  Fallback : zone fixe bas-droite utilisée")

    # 3. Sauvegarde
    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"{rib_clean}.png"
    cv2.imwrite(str(out_path), region)
    print(f"✅ Spécimen sauvegardé → {out_path}")

    # 4. Aperçu
    preview = cv2.resize(region, (400, 200))
    cv2.imshow(f"Signature cropée — RIB {rib_clean}", preview)
    print("   (appuie sur une touche pour fermer l'aperçu)")
    cv2.waitKey(0)
    cv2.destroyAllWindows()


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    crop_and_save(sys.argv[1], sys.argv[2])
