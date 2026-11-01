"""
Script d'entraînement pour le réseau siamois de vérification de signature.

Génère : models/siamese_signature.h5

Architecture :
  - Backbone : MobileNetV2 (frozen) — léger, rapide, excellent extracteur de features
  - Tête Siamoise : Dense 256 -> L2 Norm -> Embedding 128D
  - Fonction de perte : Contrastive Loss
  - Comparaison : Similarité Cosine sur les embeddings

Structure du dossier d'entraînement attendue :
  training_data/
  ├── RIB_001/          <- dossier par RIB (ou par personne)
  │   ├── sig1.png
  │   ├── sig2.png
  │   └── sig3.png
  ├── RIB_002/
  │   ├── sig1.png
  │   └── sig2.png
  └── ...

Génération des paires :
  - Paires POSITIVES (label=1) : deux signatures du même dossier
  - Paires NÉGATIVES (label=0) : deux signatures de dossiers différents
  - Distribution équilibrée 50% / 50% pour éviter le biais de classe
  - "Hard Negatives" inclus : 20% des paires négatives choisies parmi
    les individus visuellement les plus proches (SSIM élevé)

Normalisation :
  Identique à preprocess_sig() dans signature_verification.py
  (GRAY -> CLAHE -> OTSU inv -> Dilation 2x2 -> Morph Open -> 105x105 -> /255.0)

Usage :
  python scripts/train_siamese.py --data training_data/ --epochs 30 --batch 32
"""

import argparse
import random
import os
import sys
import numpy as np
import cv2
from pathlib import Path
from itertools import combinations
from sklearn.model_selection import train_test_split
from skimage.metrics import structural_similarity as ssim

import tensorflow as tf
from tensorflow.keras import layers, Model
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.callbacks import ModelCheckpoint, EarlyStopping, ReduceLROnPlateau

# -- Constantes --------------------------------------------------------------
IMG_SIZE    = (105, 105)
EMBED_DIM   = 128
HARD_NEG_RATIO = 0.20   # Fraction des paires négatives qui sont "hard"

# Dossier de sortie du modèle
BASE_DIR   = Path(__file__).resolve().parent.parent
MODEL_PATH   = BASE_DIR / "models" / "siamese_signature.keras"
ENCODER_PATH = BASE_DIR / "models" / "signature_encoder.keras"


# -- Pretraitement (identique a signature_verification.py) --------------------

def preprocess_sig(img: np.ndarray) -> np.ndarray | None:
    """
    Pipeline strictement identique à Phase 4 pour garantir la cohérence
    entre entraînement et inférence.
    """
    if img is None:
        return None

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Binarisation OTSU inversée
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Dilation minimale (2x2, 1 iter)
    kernel_dil = np.ones((2, 2), np.uint8)
    binary = cv2.dilate(binary, kernel_dil, iterations=1)

    # Nettoyage bruit
    kernel_open = np.ones((2, 2), np.uint8)
    cleaned = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel_open)

    # Normalisation
    resized = cv2.resize(cleaned, IMG_SIZE)
    return (resized.astype("float32") / 255.0)[..., np.newaxis]


def augment_sig(img: np.ndarray) -> np.ndarray:
    """
    Data augmentation légère pour la robustesse :
    - Rotation ±5° (signatures légèrement inclinées)
    - Bruit Gaussien (variations de scan)
    - Légère variation de luminosité (pression stylo)
    """
    h, w = IMG_SIZE

    # Rotation aléatoire ±5°
    angle = random.uniform(-5, 5)
    M = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    img_uint8 = (img.squeeze() * 255).astype(np.uint8)
    rotated = cv2.warpAffine(img_uint8, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    # Bruit gaussien
    noise = np.random.normal(0, 0.02, rotated.shape).astype(np.float32)
    noisy = np.clip(rotated.astype(np.float32) / 255.0 + noise, 0, 1)

    # Variation de luminosité (±10%)
    brightness = random.uniform(0.90, 1.10)
    result = np.clip(noisy * brightness, 0, 1)

    return result[..., np.newaxis].astype(np.float32)


# -- Chargement des donnees ----------------------------------------------------

def load_signatures(data_dir: str) -> dict[str, list[np.ndarray]]:
    """
    Charge toutes les signatures organisées par identité (dossier = RIB/personne).
    Retourne : {identite: [img_preprocessed, ...]}
    """
    data = {}
    exts = (".png", ".jpg", ".jpeg", ".bmp")
    data_path = Path(data_dir)

    for person_dir in sorted(data_path.iterdir()):
        if not person_dir.is_dir():
            continue
        sigs = []
        for img_path in sorted(person_dir.iterdir()):
            if img_path.suffix.lower() in exts:
                img = cv2.imread(str(img_path))
                processed = preprocess_sig(img)
                if processed is not None:
                    sigs.append(processed)
        if sigs:
            data[person_dir.name] = sigs
            print(f"  OK {person_dir.name}: {len(sigs)} signature(s)")

    return data


def generate_pairs(data: dict[str, list[np.ndarray]], augment: bool = True) -> tuple:
    """
    Génère des paires équilibrées (50% positives / 50% négatives).
    Inclut des "Hard Negatives" (≈ 20%) pour un entraînement plus robuste.

    Paires positives  (label=1) : même identité, signatures différentes
    Paires négatives  (label=0) : identités différentes
    Hard Negatives              : identités différentes mais SSIM élevé
    """
    identities = list(data.keys())
    positive_pairs, negative_pairs = [], []

    # -- Paires POSITIVES --------------------------------------------
    for ident, sigs in data.items():
        # Toutes les combinaisons de 2 signatures de la même personne
        for sig_a, sig_b in combinations(sigs, 2):
            img_a = augment_sig(sig_a) if augment else sig_a
            img_b = augment_sig(sig_b) if augment else sig_b
            positive_pairs.append((img_a, img_b, 1))

    n_pos = len(positive_pairs)
    print(f"  [Positives] Paires positives : {n_pos}")

    # -- Paires NEGATIVES ---------------------------------------------
    n_neg_hard   = int(n_pos * HARD_NEG_RATIO)
    n_neg_random = n_pos - n_neg_hard

    # Hard Negatives : trouver les paires inter-identités avec SSIM élevé
    hard_candidates = []
    id_pairs = list(combinations(identities, 2))
    random.shuffle(id_pairs)

    for id_a, id_b in id_pairs[:200]:  # Limiter la recherche pour la vitesse
        sig_a = random.choice(data[id_a])
        sig_b = random.choice(data[id_b])
        # SSIM sur les images aplaties en 2D
        score = ssim(sig_a.squeeze(), sig_b.squeeze(), data_range=1.0)
        hard_candidates.append((sig_a, sig_b, score))

    # Trier par SSIM décroissant (plus similaires = plus difficiles)
    hard_candidates.sort(key=lambda x: x[2], reverse=True)
    for sig_a, sig_b, _ in hard_candidates[:n_neg_hard]:
        img_a = augment_sig(sig_a) if augment else sig_a
        img_b = augment_sig(sig_b) if augment else sig_b
        negative_pairs.append((img_a, img_b, 0))

    # Paires négatives aléatoires pour compléter
    for _ in range(n_neg_random):
        id_a, id_b = random.sample(identities, 2)
        sig_a = random.choice(data[id_a])
        sig_b = random.choice(data[id_b])
        img_a = augment_sig(sig_a) if augment else sig_a
        img_b = augment_sig(sig_b) if augment else sig_b
        negative_pairs.append((img_a, img_b, 0))

    print(f"  [Negatives] Paires negatives : {len(negative_pairs)} ({n_neg_hard} hard + {n_neg_random} random)")

    all_pairs = positive_pairs + negative_pairs
    random.shuffle(all_pairs)

    imgs_a  = np.array([p[0] for p in all_pairs], dtype=np.float32)
    imgs_b  = np.array([p[1] for p in all_pairs], dtype=np.float32)
    labels  = np.array([p[2] for p in all_pairs], dtype=np.float32)

    return imgs_a, imgs_b, labels


# -- Architecture du reseau siamois --------------------------------------------

def build_encoder() -> Model:
    """
    Encodeur individuel (une branche du réseau siamois).

    Architecture :
      MobileNetV2 (frozen, sans couche top) -> GlobalAvgPool2D
      -> Dense(256, relu) -> L2 Normalization -> Dense(128) [Embedding]

    MobileNetV2 est préchargé sur ImageNet, ses poids sont gelés pour
    préserver les features génériques de bas niveau. Seule la tête Dense
    est entraînable.
    """
    # Prétraitement : dupliquer le canal gris en 3 canaux (MobileNetV2 attend RGB)
    inp = layers.Input(shape=(*IMG_SIZE, 1), name="sig_input")
    x   = layers.Concatenate(axis=-1, name="gray_to_rgb")([inp, inp, inp])

    # Redimensionner vers la taille minimale MobileNetV2 (96x96 minimum)
    x = layers.Resizing(96, 96)(x)

    # Backbone MobileNetV2 gelé
    backbone = MobileNetV2(input_shape=(96, 96, 3), include_top=False, weights="imagenet")
    backbone.trainable = False
    x = backbone(x, training=False)

    # Tête de classification -> Embedding
    x = layers.GlobalAveragePooling2D(name="gap")(x)
    x = layers.Dense(256, activation="relu", name="dense_256")(x)
    x = layers.Dropout(0.3)(x)
    # L2 Normalization via UnitNormalization (Keras 2.11+)
    x = layers.UnitNormalization(axis=1, name="l2_norm")(x)
    embedding = layers.Dense(EMBED_DIM, name="embedding")(x)

    return Model(inputs=inp, outputs=embedding, name="signature_encoder")


def build_siamese_model(encoder: Model) -> Model:
    """
    Construit le modèle siamois complet à partir de l'encodeur partagé.
    Sortie : similarité cosine [0, 1] calculée sur les deux embeddings.
    """
    inp_a = layers.Input(shape=(*IMG_SIZE, 1), name="input_a")
    inp_b = layers.Input(shape=(*IMG_SIZE, 1), name="input_b")

    emb_a = encoder(inp_a)
    emb_b = encoder(inp_b)

    # Similarité Cosine : dot product des vecteurs L2-normés
    # (déjà normalisés via l2_norm dans l'encodeur)
    similarity = layers.Dot(axes=1, normalize=True, name="cosine_similarity")([emb_a, emb_b])

    # Rescaler [-1,1] -> [0,1]
    output = layers.Rescaling(scale=0.5, offset=0.5, name="similarity_rescaled")(similarity)

    return Model(inputs=[inp_a, inp_b], outputs=output, name="siamese_signature")


# -- Contrastive Loss ----------------------------------------------------------

def contrastive_loss(margin: float = 0.2):
    """
    Contrastive Loss :
      L = y * (1 - sim)^2 + (1-y) * max(0, sim - margin)^2

    - Pairs positives (y=1)  : minimise (1 - sim)^2 -> pousse vers sim=1
    - Pairs négatives (y=0)  : minimise max(0, sim-margin)^2 -> pousse sous margin
    """
    def loss(y_true, y_pred):
        y_true = tf.cast(y_true, tf.float32)
        pos_loss = y_true       * tf.square(1.0 - y_pred)
        neg_loss = (1 - y_true) * tf.square(tf.maximum(0.0, y_pred - margin))
        return tf.reduce_mean(pos_loss + neg_loss)
    return loss


# -- Entrainement --------------------------------------------------------------─

def train(data_dir: str, epochs: int = 30, batch_size: int = 32):
    print("\n" + "=" * 60)
    print("  ENTRAINEMENT SigNet - Reseau Siamois de Signature")
    print("=" * 60)

    # 1. Chargement des données
    print(f"\n[1/5] [Data] Chargement des signatures depuis : {data_dir}")
    data = load_signatures(data_dir)
    if len(data) < 2:
        print("X Il faut au moins 2 identites (dossiers) pour entrainer.")
        sys.exit(1)
    print(f"  -> {len(data)} identites chargees")

    # 2. Generation des paires
    print("\n[2/5] [Pairs] Generation des paires (positives + negatives + hard negatives)...")
    imgs_a, imgs_b, labels = generate_pairs(data, augment=True)
    print(f"  -> {len(labels)} paires au total")
    print(f"  -> Positives : {int(labels.sum())} | Negatives : {int((1-labels).sum())}")

    # 3. Split Train / Validation
    print("\n[3/5] [Split] Split Train/Val (80%/20%)...")
    a_tr, a_val, b_tr, b_val, y_tr, y_val = train_test_split(
        imgs_a, imgs_b, labels, test_size=0.20, random_state=42, stratify=labels
    )
    print(f"  -> Train : {len(y_tr)} | Val : {len(y_val)}")

    # 4. Construction du modele
    print("\n[4/5] [Model] Construction du reseau siamois (MobileNetV2 backbone)...")
    encoder = build_encoder()
    model   = build_siamese_model(encoder)
    model.compile(
        optimizer=tf.keras.optimizers.Adam(learning_rate=1e-4),
        loss=contrastive_loss(margin=0.2),
        metrics=["accuracy"]
    )
    model.summary(line_length=80)

    # 5. Entrainement
    print(f"\n[5/5] [Train] Entrainement ({epochs} epochs, batch={batch_size})...")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)

    callbacks = [
        ModelCheckpoint(
            str(MODEL_PATH), monitor="val_loss",
            save_best_only=True, verbose=1
        ),
        EarlyStopping(
            monitor="val_loss", patience=7, restore_best_weights=True, verbose=1
        ),
        ReduceLROnPlateau(
            monitor="val_loss", factor=0.5, patience=3, min_lr=1e-6, verbose=1
        ),
    ]

    history = model.fit(
        [a_tr, b_tr], y_tr,
        validation_data=([a_val, b_val], y_val),
        epochs=epochs,
        batch_size=batch_size,
        callbacks=callbacks,
        verbose=1
    )

    # Resume final
    best_val_loss = min(history.history["val_loss"])
    best_val_acc  = max(history.history.get("val_accuracy", [0.0]))
    print(f"\n{'='*60}")
    print(f"  OK Entrainement termine !")
    print(f"  Meilleur val_loss  : {best_val_loss:.4f}")
    print(f"  Meilleur val_acc   : {best_val_acc:.4f}")
    
    # Sauvegarde finale de l'encodeur seul (pour signature_verification.py)
    print(f"  Sauvegarde de l'encodeur... ")
    encoder.save(str(ENCODER_PATH))
    
    print(f"  Modele complet sauve : {MODEL_PATH}")
    print(f"  Encodeur sauve       : {ENCODER_PATH}")
    print(f"{'='*60}\n")

    return history


# -- Point d'entree ------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Entraînement du réseau SigNet siamois pour la vérification de signature."
    )
    parser.add_argument(
        "--data", required=True, type=str,
        help="Dossier contenant les sous-dossiers de signatures (un dossier = une identité/RIB)"
    )
    parser.add_argument(
        "--epochs", default=30, type=int,
        help="Nombre d'epochs d'entraînement (défaut: 30)"
    )
    parser.add_argument(
        "--batch", default=32, type=int,
        help="Taille du batch (défaut: 32)"
    )
    args = parser.parse_args()

    if not os.path.isdir(args.data):
        print(f"X Dossier introuvable : {args.data}")
        sys.exit(1)

    train(args.data, epochs=args.epochs, batch_size=args.batch)
