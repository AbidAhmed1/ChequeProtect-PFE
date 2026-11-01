"""
training/train_simple_v2.py  (train_phase1.py)
================================================
CNN MobileNetV2 — Dataset corrigé + fix Keras 3.x.

CORRECTION focal_loss :
  AVANT : fonction custom → ValueError dtype='string' avec Keras 3.x
  APRES : tf.keras.losses.BinaryFocalCrossentropy (intégré Keras 3.x)
          → aucun conflit de types
          → pas besoin de custom_objects dans load_model

DATASET :
  REAL = tout chèque bancaire (nouveaux 2025 + vieux sans QR)
  FAKE = tout ce qui N'EST PAS un chèque (factures, reçus, documents)
"""

import os, json, time, random, shutil
import numpy as np
from pathlib import Path

os.environ["TF_CPP_MIN_LOG_LEVEL"]  = "2"
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["PYTHONHASHSEED"]        = "42"

random.seed(42)
np.random.seed(42)

import tensorflow as tf
tf.random.set_seed(42)

from tensorflow.keras import layers, Model, optimizers, callbacks
from tensorflow.keras.applications import MobileNetV2
from tensorflow.keras.preprocessing.image import ImageDataGenerator

DATASET_DIR = Path(r"D:\projet-pfe\ai-tunicheque\data\cheques_dataset")
SAVE_DIR    = Path(r"D:\projet-pfe\ai-tunicheque\saved_models")
SAVE_DIR.mkdir(exist_ok=True)

IMG_SIZE   = (224, 224)
BATCH_SIZE = 16
SEED       = 42

print()
print("="*65)
print("  CNN — Dataset corrigé (chèques vs non-chèques)")
print("  Fix : BinaryFocalCrossentropy (Keras 3.x natif)")
print("="*65)

# ── Vérification dataset ───────────────────────────────────────────────────
real_dir = DATASET_DIR / "real"
fake_dir = DATASET_DIR / "fake"

n_real = len([f for f in real_dir.glob("*")
              if f.suffix.lower() in {".jpg",".jpeg",".png"}]) \
    if real_dir.exists() else 0
n_fake = len([f for f in fake_dir.glob("*")
              if f.suffix.lower() in {".jpg",".jpeg",".png",".bmp"}]) \
    if fake_dir.exists() else 0

print()
print("  Dataset :")
print("    REAL : {} images (chèques nouveaux + anciens)".format(n_real))
print("    FAKE : {} images (factures, reçus, documents)".format(n_fake))

if n_real == 0 or n_fake == 0:
    print("  ERREUR : Dataset vide ! Exécuter prepare_v3.py")
    exit(1)


# ══════════════════════════════════════════════════════════════════════════
#  GENERATEURS
# ══════════════════════════════════════════════════════════════════════════

train_gen = ImageDataGenerator(
    rescale=1.0/255, validation_split=0.20,
    rotation_range=8, brightness_range=[0.75, 1.30],
    zoom_range=0.10, width_shift_range=0.05,
    height_shift_range=0.05, fill_mode="constant", cval=1.0,
)
val_gen = ImageDataGenerator(rescale=1.0/255, validation_split=0.20)

print()
print("  Chargement...")

tg = train_gen.flow_from_directory(
    str(DATASET_DIR), target_size=IMG_SIZE,
    batch_size=BATCH_SIZE, class_mode="binary",
    subset="training", seed=SEED, shuffle=True)

vg = val_gen.flow_from_directory(
    str(DATASET_DIR), target_size=IMG_SIZE,
    batch_size=BATCH_SIZE, class_mode="binary",
    subset="validation", seed=SEED, shuffle=False)

print("  Classes : {}".format(tg.class_indices))
print("  Train: {}  Val: {}".format(tg.samples, vg.samples))

real_label = tg.class_indices.get("real", 1)
fake_label = 1 - real_label
with open(str(SAVE_DIR / "class_indices.json"), "w") as f:
    json.dump(tg.class_indices, f, indent=2)

# Class weights
nt = tg.samples
nr = int(nt * (n_real / (n_real + n_fake)))
nf = int(nt * (n_fake / (n_real + n_fake)))
class_weight = {
    real_label: nt / (2.0 * max(nr, 1)),
    fake_label: nt / (2.0 * max(nf, 1)) * 2.0,
}
print("  class_weight real={:.2f} fake={:.2f}".format(
    class_weight[real_label], class_weight[fake_label]))


# ══════════════════════════════════════════════════════════════════════════
#  MODELE
# ══════════════════════════════════════════════════════════════════════════

def build(trainable=0):
    base = MobileNetV2(weights="imagenet", include_top=False,
                       input_shape=(*IMG_SIZE, 3))
    if trainable == 0:
        base.trainable = False
    else:
        base.trainable = True
        for l in base.layers[:-trainable]:
            l.trainable = False
    x = tf.keras.Input(shape=(*IMG_SIZE, 3))
    h = base(x, training=(trainable > 0))
    h = layers.GlobalAveragePooling2D()(h)
    h = layers.BatchNormalization()(h)
    h = layers.Dense(256, "relu",
                     kernel_regularizer=tf.keras.regularizers.l2(1e-4))(h)
    h = layers.Dropout(0.60)(h)
    h = layers.Dense(128, "relu",
                     kernel_regularizer=tf.keras.regularizers.l2(1e-5))(h)
    h = layers.Dropout(0.50)(h)
    return Model(x, layers.Dense(1, "sigmoid")(h)), base


def cbs(name, lr_f=0.3, p_es=15, p_lr=5):
    return [
        callbacks.ModelCheckpoint(
            str(SAVE_DIR / "{}.keras".format(name)),
            monitor="val_accuracy", save_best_only=True,
            mode="max", verbose=1),
        callbacks.EarlyStopping(
            monitor="val_accuracy", patience=p_es,
            restore_best_weights=True, verbose=1),
        callbacks.ReduceLROnPlateau(
            monitor="val_loss", factor=lr_f,
            patience=p_lr, min_lr=1e-8, verbose=1),
    ]


# ══════════════════════════════════════════════════════════════════════════
#  PHASE 1 — Base gelée
#
#  FIX : BinaryFocalCrossentropy (intégré Keras 3.x)
#  AVANT : focal_loss() custom → ValueError dtype='string'
#  APRES : tf.keras.losses.BinaryFocalCrossentropy → aucun conflit
# ══════════════════════════════════════════════════════════════════════════

print()
print("="*65)
print("  PHASE 1 — Base gelée + BinaryFocalCrossentropy")
print("="*65)

t0    = time.time()
m, _  = build(0)

m.compile(
    optimizer = optimizers.Adam(5e-4),
    loss      = tf.keras.losses.BinaryFocalCrossentropy(
        gamma       = 2.0,
        from_logits = False,
    ),
    metrics   = ["accuracy"],
)

print("  Params trainables : {:,}".format(
    sum(p.numpy().size for p in m.trainable_variables)))
print("  Loss : BinaryFocalCrossentropy(gamma=2.0)")

ha     = m.fit(tg, epochs=30, validation_data=vg,
               class_weight=class_weight,
               callbacks=cbs("best_phaseA"), verbose=1)
best_a = max(ha.history["val_accuracy"])
print()
print("  Phase 1 — val_accuracy : {:.1f}%".format(best_a * 100))


# ══════════════════════════════════════════════════════════════════════════
#  PHASE 2 — Fine-tuning 30 couches
#
#  FIX : load_model SANS custom_objects (plus nécessaire)
#  AVANT : custom_objects={"loss": focal_loss(...)} → crash
#  APRES : load_model direct → Keras recharge BinaryFocalCrossentropy seul
# ══════════════════════════════════════════════════════════════════════════

print()
print("="*65)
print("  PHASE 2 — Fine-tuning 30 couches + BinaryFocalCrossentropy")
print("="*65)

# CORRECTION : pas de custom_objects
m2 = tf.keras.models.load_model(str(SAVE_DIR / "best_phaseA.keras"))

# Geler tout puis dégeler les 30 dernières couches MobileNetV2
for l in m2.layers:
    l.trainable = False

for l in m2.layers:
    if "mobilenetv2" in l.name.lower():
        n = len(l.layers)
        for s in l.layers[:-30]: s.trainable = False
        for s in l.layers[-30:]: s.trainable = True
        print("  MobileNetV2 : {} couches, 30 dernières dégelées".format(n))
        break

# Dégeler aussi les couches Dense/BN finales
for l in m2.layers:
    if isinstance(l, (layers.Dense, layers.Dropout, layers.BatchNormalization)):
        l.trainable = True

m2.compile(
    optimizer = optimizers.Adam(5e-6),
    loss      = tf.keras.losses.BinaryFocalCrossentropy(
        gamma       = 3.0,
        from_logits = False,
    ),
    metrics   = ["accuracy"],
)

print("  Params trainables : {:,}".format(
    sum(p.numpy().size for p in m2.trainable_variables)))
print("  Loss : BinaryFocalCrossentropy(gamma=3.0)")

hb     = m2.fit(tg, epochs=30, validation_data=vg,
                class_weight={real_label: 1.0,
                              fake_label: class_weight[fake_label] + 1},
                callbacks=cbs("best_phaseB", 0.2, 10, 4), verbose=1)
best_b = max(hb.history["val_accuracy"])
print()
print("  Phase 2 — val_accuracy : {:.1f}%".format(best_b * 100))


# ── Meilleur modèle ────────────────────────────────────────────────────────

best_overall = max(best_a, best_b)
src = "best_phaseA.keras" if best_a >= best_b else "best_phaseB.keras"
dst = str(SAVE_DIR / "best_model_phaseA.keras")
shutil.copy2(str(SAVE_DIR / src), dst)
print()
print("  Meilleur : Phase {} ({:.1f}%) → {}".format(
    "1" if best_a >= best_b else "2", best_overall * 100, dst))


# ══════════════════════════════════════════════════════════════════════════
#  ÉVALUATION FINALE + ANALYSE PAR SEUIL
# ══════════════════════════════════════════════════════════════════════════

print()
print("  Évaluation + analyse par seuil...")

# CORRECTION : load_model SANS custom_objects
fm = tf.keras.models.load_model(dst)
vg.reset()
preds  = fm.predict(vg, verbose=0).flatten()
y_true = vg.classes
best_th, best_f1 = 0.50, 0.0

print()
print("  {:6s} {:8s} {:8s} {:8s} {:8s}  {:10s}  {:10s}".format(
    "Seuil", "Acc", "Prec", "Recall", "F1",
    "Non-chèq OK", "Chèque OK"))
print("  " + "-"*70)

n_r = sum(y_true == real_label)
n_f = sum(y_true == fake_label)

for th in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70]:
    yp = (preds >= th).astype(int)
    if real_label == 0: yp = 1 - yp
    tp = sum(1 for t, p in zip(y_true, yp)
             if t == real_label and p == real_label)
    tn = sum(1 for t, p in zip(y_true, yp)
             if t == fake_label and p == fake_label)
    fp = sum(1 for t, p in zip(y_true, yp)
             if t == fake_label and p == real_label)
    fn = sum(1 for t, p in zip(y_true, yp)
             if t == real_label and p == fake_label)
    acc = (tp + tn) / max(len(y_true), 1)
    pre = tp / max(tp + fp, 1)
    rec = tp / max(tp + fn, 1)
    f1  = 2 * pre * rec / max(pre + rec, 1e-8)
    m_  = " ←" if 0.60 <= th <= 0.70 else ""
    print("  {:.2f}  {:6.1f}%  {:6.1f}%  {:6.1f}%  {:.3f}  "
          "{:4d}/{:<4d}  {:4d}/{:<4d}{}".format(
        th, acc*100, pre*100, rec*100, f1,
        tn, n_f, tp, n_r, m_))
    if f1 > best_f1:
        best_f1 = f1
        best_th = th

print()
print("  Seuil optimal : {:.2f}".format(best_th))

# Matrice finale au seuil optimal
vg.reset()
yp_opt = (fm.predict(vg, verbose=0).flatten() >= best_th).astype(int)
if real_label == 0: yp_opt = 1 - yp_opt
tp=sum(1 for t,p in zip(y_true,yp_opt) if t==real_label and p==real_label)
tn=sum(1 for t,p in zip(y_true,yp_opt) if t==fake_label and p==fake_label)
fp=sum(1 for t,p in zip(y_true,yp_opt) if t==fake_label and p==real_label)
fn=sum(1 for t,p in zip(y_true,yp_opt) if t==real_label and p==fake_label)
acc=(tp+tn)/max(len(y_true),1)
pre=tp/max(tp+fp,1); rec=tp/max(tp+fn,1)
f1_=2*pre*rec/max(pre+rec,1e-8)

print()
print("  Matrice de confusion (seuil={:.2f}) :".format(best_th))
print("                     Prédit chèque  Prédit non-chèque")
print("  Vrai chèque   :       {:4d}              {:4d}".format(tp, fn))
print("  Vrai non-chèque :     {:4d}              {:4d}".format(fp, tn))
print()
print("  Accuracy  : {:.1f}%".format(acc*100))
print("  Precision : {:.1f}%".format(pre*100))
print("  Recall    : {:.1f}%".format(rec*100))
print("  F1-Score  : {:.3f}".format(f1_))

elapsed = time.time() - t0

with open(str(SAVE_DIR / "config_phase1.json"), "w") as f:
    json.dump({
        "modele":        "MobileNetV2_BinaryFocalCrossentropy",
        "img_size":      list(IMG_SIZE),
        "accuracy":      round(acc, 4),
        "precision":     round(pre, 4),
        "recall":        round(rec, 4),
        "f1":            round(f1_, 4),
        "duree_min":     round(elapsed / 60, 1),
        "class_indices": tg.class_indices,
        "seuils": {
            "threshold_real": best_th,
            "threshold_fake": round(best_th - 0.20, 2),
        }
    }, f, indent=2)

print()
print("="*65)
print("  TERMINÉ en {:.1f} min".format(elapsed / 60))
print("  Phase 1 : {:.1f}%  Phase 2 : {:.1f}%".format(
    best_a*100, best_b*100))
print()
print("  COPIER CES SEUILS dans phase1_identification.py :")
print("    threshold_real = {:.2f}".format(best_th))
print("    threshold_fake = {:.2f}".format(round(best_th - 0.20, 2)))
print("="*65)