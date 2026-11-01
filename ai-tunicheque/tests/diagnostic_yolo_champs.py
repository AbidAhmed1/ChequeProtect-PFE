"""
tests/diagnostic_yolo_champs.py
─────────────────────────────────────────────────────────────────
Diagnostic : teste chaque YOLO spécialisé sur une image de chèque
→ Affiche les détections + sauvegarde les crops pour inspection visuelle

Usage :
    python tests/diagnostic_yolo_champs.py Chequetest/chequeN.jpg
"""

import sys, cv2, numpy as np
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

IMG_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "Chequetest" / "chequeN.jpg"
OUT_DIR  = ROOT / "debug_crops"
OUT_DIR.mkdir(exist_ok=True)

MODELS = {
    "YOLO-Tireur"   : ROOT / "saved_models/yolo_tireur/best_tireur.pt",
    "YOLO-DateLieu" : ROOT / "saved_models/yolo_datelieu/best_datelieu.pt",
    "YOLO-Benef"    : ROOT / "saved_models/yolo_benef/best_beneficiaire.pt",
    "YOLO-Agence"   : ROOT / "saved_models/yolo_agence/best.pt",
    "YOLO-Montant"  : ROOT / "saved_models/yolo_montant/yolo_montant_best.pt",
}

CONF_THRESHOLDS = [0.25, 0.15, 0.10, 0.05]

def _sep(c="─", n=60): print(c * n)

def test_model(name, model_path, image):
    from ultralytics import YOLO
    print(f"\n{'═'*60}")
    print(f"  {name}  ({model_path.name})")
    _sep()

    if not model_path.exists():
        print(f"  ❌ Fichier introuvable : {model_path}")
        return

    model = YOLO(str(model_path))
    h, w = image.shape[:2]
    print(f"  Image : {w}x{h} px")

    any_found = False
    for conf in CONF_THRESHOLDS:
        results = model(image, conf=conf, verbose=False)
        boxes = results[0].boxes if results else None

        if boxes and len(boxes) > 0:
            print(f"\n  seuil conf={conf:.2f} → {len(boxes)} détection(s) :")
            for i, box in enumerate(boxes):
                cls_id = int(box.cls[0])
                bc     = float(box.conf[0])
                x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
                print(f"    [{i}] cls={cls_id}  conf={bc:.3f}  "
                      f"bbox=({x1},{y1})→({x2},{y2})  "
                      f"taille={x2-x1}x{y2-y1}")

                if i == 0 and not any_found:
                    crop = image[max(0,y1-8):min(h,y2+8),
                                 max(0,x1-8):min(w,x2+8)]
                    if crop.size > 0:
                        fname = OUT_DIR / f"{name.replace('-','_').lower()}_crop.jpg"
                        cv2.imwrite(str(fname), crop)
                        print(f"    💾 Crop sauvegardé : {fname.name}")
            any_found = True
            break   # on s'arrête au premier seuil qui trouve quelque chose
        else:
            print(f"  conf={conf:.2f} → rien détecté", end="  ")

    if not any_found:
        print(f"\n  ⚠️  Aucune détection même à conf=0.05")
        print(f"     → Le modèle ne reconnaît pas ce chèque.")
        print(f"     → Vérifiez le dataset d'entraînement / la classe 0.")


def main():
    if not IMG_PATH.exists():
        print(f"❌ Image introuvable : {IMG_PATH}")
        return

    image = cv2.imread(str(IMG_PATH))
    if image is None:
        print(f"❌ Impossible de lire : {IMG_PATH}")
        return

    print(f"\n  Chèque : {IMG_PATH.name}")
    print(f"  Crops  : {OUT_DIR}")

    try:
        from ultralytics import YOLO
    except ImportError:
        print("❌ ultralytics non installé")
        return

    for name, path in MODELS.items():
        test_model(name, path, image)

    print(f"\n{'═'*60}")
    print(f"  Ouvrez {OUT_DIR} pour voir les crops détectés.")
    print(f"{'═'*60}\n")


if __name__ == "__main__":
    main()