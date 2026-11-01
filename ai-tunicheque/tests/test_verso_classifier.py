"""
test_verso_classifier.py
=========================
Tester le modèle entraîné sur de nouvelles images.

Usage :
    python test_verso_classifier.py                    → test sur dataset complet
    python test_verso_classifier.py ma_photo.jpg       → test sur une image
"""

import os, sys
import cv2
import numpy as np
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import tensorflow as tf

MODEL_PATH = Path("saved_models/verso_classifier.keras")

if not MODEL_PATH.exists():
    print(f"❌ Modèle introuvable : {MODEL_PATH}")
    print("   → Lancez d'abord : python train_verso_classifier.py")
    sys.exit(1)

print(f"📂 Chargement du modèle : {MODEL_PATH}")
try:
    import tf_keras
    model = tf_keras.models.load_model(str(MODEL_PATH), compile=False)
except Exception:
    model = tf.keras.models.load_model(str(MODEL_PATH), compile=False)

print("  ✅ Modèle chargé\n")


def predict_image(img_path: str) -> dict:
    """Prédire si un verso est imprimé ou authentique."""
    img = cv2.imread(img_path)
    if img is None:
        return {"error": f"Impossible de lire : {img_path}"}

    img_rgb   = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_res   = cv2.resize(img_rgb, (224, 224))
    img_norm  = img_res.astype(np.float32) / 255.0
    img_batch = np.expand_dims(img_norm, 0)

    pred  = float(model.predict(img_batch, verbose=0)[0][0])
    label = "AUTHENTIQUE ✅" if pred > 0.5 else "IMPRIMÉ ❌"
    conf  = pred if pred > 0.5 else 1.0 - pred

    return {
        "fichier":  Path(img_path).name,
        "score":    round(pred, 4),
        "decision": label,
        "confiance": f"{conf:.1%}",
    }


# ── Test sur une image spécifique ─────────────────────────────────
if len(sys.argv) > 1:
    result = predict_image(sys.argv[1])
    print(f"  Fichier  : {result['fichier']}")
    print(f"  Score    : {result['score']} (0=imprimé, 1=authentique)")
    print(f"  Décision : {result['decision']}")
    print(f"  Confiance: {result['confiance']}")
    sys.exit(0)

# ── Test sur tout le dataset ───────────────────────────────────────
DATASET_DIR = Path("data/verso_dataset")
print("🧪 TEST SUR LE DATASET COMPLET")
print("-" * 50)

for classe in ["verso_vrai", "verso_imprime"]:
    classe_dir = DATASET_DIR / classe
    if not classe_dir.exists():
        continue
    imgs = list(classe_dir.glob("*.jpg")) + list(classe_dir.glob("*.jpeg")) + list(classe_dir.glob("*.png"))

    # Tester seulement les images originales (pas les augmentées)
    originals = [f for f in imgs if not f.name.startswith("aug_")]

    print(f"\n📁 {classe}/ ({len(originals)} images originales)")
    correct = 0
    for img_path in originals:
        r = predict_image(str(img_path))
        if "error" in r:
            continue
        expected = "AUTHENTIQUE" if "vrai" in classe else "IMPRIMÉ"
        ok = expected in r["decision"]
        status = "✅" if ok else "❌"
        print(f"  {status} {r['fichier'][:30]:30s} → {r['decision']} ({r['confiance']})")
        if ok:
            correct += 1

    if originals:
        print(f"  Précision : {correct}/{len(originals)} = {correct/len(originals):.0%}")

print("\n" + "=" * 50)
print("  Test rapide sur les images de test disponibles :")
for test_img in ["verso_biat.jpg", "chequeR.jpg", "verso_biat_2.jpg"]:
    if Path(test_img).exists():
        r = predict_image(test_img)
        print(f"  {r['fichier']:25s} → {r['decision']} ({r['confiance']})")
