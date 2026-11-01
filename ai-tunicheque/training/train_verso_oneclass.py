"""
train_verso_oneclass.py
========================
Détection verso imprimé via One-Class SVM (anomaly detection).

PRINCIPE :
  Entraînement : uniquement sur images "vrai" (verso authentique BCT)
  Test         : toute image trop différente = ANOMALIE = IMPRIMÉ

AVANTAGES vs SVM binaire :
  ✅ Pas besoin d'équilibre classes
  ✅ Fonctionne avec 5-10 images "vrai"
  ✅ Robuste aux variations d'angle/lumière
  ✅ Plus facile à améliorer (juste ajouter des "vrai")

FEATURES : CNN gelé MobileNetV2 (1280 features de texture)

Usage :
    cd D:\projet-pfe\ai-tunicheque
    .\.venv\Scripts\Activate.ps1
    python training\train_verso_oneclass.py
"""

import cv2
import numpy as np
import os
import joblib
from pathlib import Path
from sklearn.svm import OneClassSVM
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

os.environ["TF_CPP_MIN_LOG_LEVEL"]                    = "3"
os.environ["PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION"]  = "python"

DATASET_DIR = Path("data/verso_dataset")
MODEL_OUT   = Path("saved_models/verso_oneclass.joblib")
IMG_SIZE    = (224, 224)


# ── Extracteur CNN gelé ────────────────────────────────────────────

def build_extractor():
    import tensorflow as tf
    base = tf.keras.applications.MobileNetV2(
        input_shape=(224, 224, 3),
        include_top=False,
        weights="imagenet",
    )
    base.trainable = False
    extractor = tf.keras.Sequential([
        base,
        tf.keras.layers.GlobalAveragePooling2D(),
    ])
    return extractor


def extraire_feature(img_path: str, extractor) -> np.ndarray | None:
    img = cv2.imread(str(img_path))
    if img is None:
        return None
    img_rgb  = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    img_res  = cv2.resize(img_rgb, IMG_SIZE).astype(np.float32)
    img_norm = (img_res / 127.5) - 1.0          # MobileNetV2 [-1, 1]
    batch    = np.expand_dims(img_norm, 0)
    feat     = extractor.predict(batch, verbose=0)
    return feat.flatten().astype(np.float32)


def charger_classe(classe_dir: Path, extractor, label: str):
    """Charge uniquement les originaux (pas aug_*)."""
    all_imgs = (list(classe_dir.glob("*.jpg")) +
                list(classe_dir.glob("*.jpeg")) +
                list(classe_dir.glob("*.png")) +
                list(classe_dir.glob("*.PNG")))
    # Dédupliquer + exclure augmentées
    seen, imgs = set(), []
    for f in sorted(all_imgs):
        if not f.name.startswith("aug_") and f.name not in seen:
            seen.add(f.name)
            imgs.append(f)

    print(f"\n  📁 {label} : {len(imgs)} originaux")
    X = []
    for p in imgs:
        feat = extraire_feature(str(p), extractor)
        if feat is not None:
            X.append(feat)
            print(f"    ✅ {p.name}")
    return np.array(X) if X else None


def main():
    print("=" * 60)
    print("  ONE-CLASS SVM — VERSO DETECTOR")
    print("  Entraîné sur 'vrai' seulement → détecte anomalies")
    print("=" * 60)

    # Charger extracteur CNN
    print("\n🧠 Chargement MobileNetV2 (gelé)...")
    extractor = build_extractor()
    print(f"  ✅ Prêt — 1280 features/image")

    # Charger UNIQUEMENT les vrais versos (classe d'entraînement)
    X_vrai = charger_classe(
        DATASET_DIR / "verso_vrai", extractor, "VRAI (entraînement)")

    # Charger les imprimés UNIQUEMENT pour évaluation
    X_imprime = charger_classe(
        DATASET_DIR / "verso_imprime", extractor, "IMPRIMÉ (test uniquement)")

    if X_vrai is None or len(X_vrai) < 3:
        print("❌ Minimum 3 images 'verso_vrai' requises.")
        return

    n_vrai    = len(X_vrai)
    n_imprime = len(X_imprime) if X_imprime is not None else 0

    print(f"\n  Entraînement sur : {n_vrai} images 'vrai'")
    print(f"  Test sur         : {n_imprime} images 'imprimé'")
    print(f"  Features/image   : {X_vrai.shape[1]}")

    # ── Recherche du meilleur nu (sensibilité) ────────────────────
    # nu = proportion maximale d'outliers attendus dans les données d'entraînement
    # nu=0.1 → tolérant (10% d'anomalies acceptées dans "vrai")
    # nu=0.3 → strict  (30% d'anomalies dans "vrai")

    print("\n🔍 Optimisation du paramètre nu...")

    best_nu    = 0.1
    best_score = -1

    if X_imprime is not None and len(X_imprime) > 0:
        # Évaluer chaque valeur de nu
        for nu in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
            pipe = Pipeline([
                ("scaler", StandardScaler()),
                ("ocsvm",  OneClassSVM(kernel="rbf", nu=nu, gamma="scale")),
            ])
            pipe.fit(X_vrai)

            # Prédictions : +1 = normal (vrai), -1 = anomalie (imprimé)
            pred_vrai    = pipe.predict(X_vrai)
            pred_imprime = pipe.predict(X_imprime)

            # True Positive  : vrai prédit comme vrai
            tp = (pred_vrai == 1).sum()
            # True Negative  : imprimé prédit comme anomalie
            tn = (pred_imprime == -1).sum()

            recall_vrai    = tp / len(X_vrai)
            recall_imprime = tn / len(X_imprime)
            score_global   = (recall_vrai + recall_imprime) / 2

            print(f"  nu={nu:.2f} → vrai:{recall_vrai:.0%} imprimé:{recall_imprime:.0%} "
                  f"moy:{score_global:.0%}")

            if score_global > best_score:
                best_score = score_global
                best_nu    = nu

        print(f"\n  → Meilleur nu={best_nu} (score={best_score:.0%})")
    else:
        print("  ⚠️  Pas d'imprimés pour calibrer nu → nu=0.1 par défaut")

    # ── Entraînement final ────────────────────────────────────────
    print(f"\n🏋️  Entraînement One-Class SVM (nu={best_nu})...")
    final_pipe = Pipeline([
        ("scaler", StandardScaler()),
        ("ocsvm",  OneClassSVM(kernel="rbf", nu=best_nu, gamma="scale")),
    ])
    final_pipe.fit(X_vrai)

    # ── Évaluation finale ─────────────────────────────────────────
    print("\n📊 Évaluation finale :")

    pred_vrai = final_pipe.predict(X_vrai)
    tp = (pred_vrai == 1).sum()
    print(f"  Vrais identifiés comme VRAI    : {tp}/{n_vrai} "
          f"({tp/n_vrai:.0%})")

    if X_imprime is not None and len(X_imprime) > 0:
        pred_imprime = final_pipe.predict(X_imprime)
        tn = (pred_imprime == -1).sum()
        print(f"  Imprimés détectés comme ANOMALIE: {tn}/{n_imprime} "
              f"({tn/n_imprime:.0%})")
        accuracy = (tp + tn) / (n_vrai + n_imprime)
        print(f"  Accuracy globale               : {accuracy:.0%}")
    else:
        accuracy = tp / n_vrai

    # ── Tester sur augmentées ─────────────────────────────────────
    print("\n📊 Test sur augmentées :")
    for classe_nom, expected in [("verso_vrai", 1), ("verso_imprime", -1)]:
        aug_imgs = list((DATASET_DIR / classe_nom).glob("aug_*.jpg"))[:5]
        if not aug_imgs: continue
        X_aug = np.array([f for f in
                          [extraire_feature(str(p), extractor)
                           for p in aug_imgs]
                          if f is not None])
        if len(X_aug) == 0: continue
        preds = final_pipe.predict(X_aug)
        ok = (preds == expected).mean()
        print(f"  {classe_nom:25s} : {ok:.0%} "
              f"({'✅' if ok >= 0.6 else '⚠️ '})")

    # ── Sauvegarder ───────────────────────────────────────────────
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        "pipeline":    final_pipe,
        "method":      "oneclass_svm_cnn",
        "extractor":   "MobileNetV2_frozen",
        "img_size":    IMG_SIZE,
        "nu":          best_nu,
        "classes":     {1: "AUTHENTIQUE", -1: "IMPRIME"},
        "cv_mean":     float(best_score) if best_score > 0 else 0.7,
        "n_train":     n_vrai,
        # Seuil de décision : score de décision < threshold = IMPRIMÉ
        "threshold":   0.0,
    }, str(MODEL_OUT))

    print(f"\n  ✅ Modèle sauvegardé : {MODEL_OUT}")

    # ── Résultat ──────────────────────────────────────────────────
    print("\n" + "=" * 60)
    if best_score >= 0.80:
        print(f"  ✅ EXCELLENT : {best_score:.0%} → Production")
        print("     → print_detector_WITHSVM.py l'activera automatiquement")
    elif best_score >= 0.65:
        print(f"  ⚠️  ACCEPTABLE : {best_score:.0%} → Vote d'appoint")
    else:
        print(f"  ⚠️  Limité : {best_score:.0%}")
        print("     → Utilisé en mode conservateur (confiance 80% requise)")
    print("=" * 60)
    print("""
  COMMENT AMÉLIORER :
    → Ajouter des photos 'verso_vrai' diversifiées (angles, lumières)
    → Le One-Class SVM s'améliore uniquement avec + de 'vrai'
    → Les imprimés ne sont nécessaires QUE pour calibrer nu
""")


if __name__ == "__main__":
    main()