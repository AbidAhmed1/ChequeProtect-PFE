"""
training/train_yolo.py
=======================
Entrainement YOLO — Detection des zones du cheque tunisien.

CORRECTIONS vs version precedente :
  1. 'brightness' -> 'hsv_v'  (parametre YOLO correct)
  2. valid=0 -> le script cree automatiquement un split 80/20

CLASSES A ANNOTER (Roboflow) :
  0 : montant_plafond    "Montant max DT 5000"
  1 : numero_cheque      "Cheque n 4122752"
  2 : rib_cmc7           bande magnetique bas
  3 : date               "Le 19/09/2025"
  4 : beneficiaire       "Payez a l ordre de..."
  5 : montant_chiffres   montant manuscrit chiffres
  6 : montant_lettres    montant manuscrit lettres
  7 : signature          zone signature

USAGE :
  pip install ultralytics pyyaml
  python training/train_yolo.py
"""

import os, yaml, shutil, random
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────────────
ROOT    = Path(r"D:\projet-pfe\ai-tunicheque")
DATASET = ROOT / "training" / "yolo_dataset"
SAVE    = ROOT / "saved_models"
SAVE.mkdir(exist_ok=True)

CLASSES = [
    "montant_plafond",
    "numero_cheque",
    "rib_cmc7",
    "date",
    "beneficiaire",
    "montant_chiffres",
    "montant_lettres",
    "signature",
]

EPOCHS = 100
IMGSZ  = 640
BATCH  = 8     # reduire a 4 si memoire insuffisante


# ══════════════════════════════════════════════════════════════════════════
#  CREER UN SPLIT VALIDATION DEPUIS TRAIN
#  Utilise quand Roboflow n'a pas cree de dossier valid/
#  (arrive quand < 10 images au moment de l'export)
# ══════════════════════════════════════════════════════════════════════════

def creer_split_validation(train_img_dir: Path, train_lbl_dir: Path,
                           valid_img_dir: Path, valid_lbl_dir: Path,
                           ratio_val: float = 0.20):
    """
    Prend 20% des images de train et les copie dans valid.
    Appele automatiquement si valid/ est vide.
    """
    valid_img_dir.mkdir(parents=True, exist_ok=True)
    valid_lbl_dir.mkdir(parents=True, exist_ok=True)

    imgs = list(train_img_dir.glob("*.jpg")) + \
           list(train_img_dir.glob("*.png")) + \
           list(train_img_dir.glob("*.jpeg"))

    if not imgs:
        return 0

    random.seed(42)
    random.shuffle(imgs)
    n_val = max(1, int(len(imgs) * ratio_val))
    imgs_val = imgs[:n_val]

    for img in imgs_val:
        lbl = train_lbl_dir / (img.stem + ".txt")
        shutil.copy2(img, valid_img_dir / img.name)
        if lbl.exists():
            shutil.copy2(lbl, valid_lbl_dir / lbl.name)

    print("  Split 80/20 cree : {} -> valid".format(n_val))
    return n_val


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 1 — VERIFIER LE DATASET
# ══════════════════════════════════════════════════════════════════════════

def verifier_dataset() -> str:
    """
    Detecte le format du dataset et prepare le data.yaml.
    Cree automatiquement un split valid si necessaire.
    """
    print()
    print("  Verification dataset...")

    # ── Format Roboflow : train/images/ ──────────────────────────────────
    yaml_path   = DATASET / "data.yaml"
    train_img   = DATASET / "train" / "images"
    train_lbl   = DATASET / "train" / "labels"
    valid_img   = DATASET / "valid" / "images"
    valid_lbl   = DATASET / "valid" / "labels"

    n_train = len(list(train_img.glob("*"))) if train_img.exists() else 0

    if n_train > 0:
        print("  Format Roboflow detecte")
        print("  Train : {} images".format(n_train))

        # Creer valid si vide ou absent
        n_valid = len(list(valid_img.glob("*"))) if valid_img.exists() else 0
        if n_valid == 0:
            print("  Valid : 0 images -> creation split automatique 80/20")
            n_valid = creer_split_validation(
                train_img, train_lbl, valid_img, valid_lbl, ratio_val=0.20)
        else:
            print("  Valid : {} images".format(n_valid))

        # Ecrire/corriger data.yaml
        if yaml_path.exists():
            with open(yaml_path) as f:
                d = yaml.safe_load(f) or {}
        else:
            d = {}

        d["path"]  = str(DATASET)
        d["train"] = "train/images"
        d["val"]   = "valid/images"
        d["nc"]    = len(CLASSES)
        d["names"] = CLASSES

        with open(yaml_path, "w") as f:
            yaml.dump(d, f, allow_unicode=True, default_flow_style=False)

        print("  data.yaml mis a jour")
        print("  Train final : {}  Valid : {}".format(n_train, n_valid))
        return str(yaml_path)

    # ── Format LabelImg : images/train/ ──────────────────────────────────
    li_train = DATASET / "images" / "train"
    n_li     = len(list(li_train.glob("*"))) if li_train.exists() else 0

    if n_li > 0:
        print("  Format LabelImg detecte : {} images".format(n_li))
        li_valid = DATASET / "images" / "val"
        n_lv     = len(list(li_valid.glob("*"))) if li_valid.exists() else 0
        if n_lv == 0:
            creer_split_validation(
                li_train, DATASET / "labels" / "train",
                li_valid, DATASET / "labels" / "val")
        d = {
            "path": str(DATASET), "train":"images/train", "val":"images/val",
            "nc": len(CLASSES), "names": CLASSES,
        }
        with open(yaml_path, "w") as f:
            yaml.dump(d, f, allow_unicode=True, default_flow_style=False)
        return str(yaml_path)

    # ── Aucun dataset ─────────────────────────────────────────────────────
    print()
    print("  ERREUR : Aucun dataset trouve dans :")
    print("    {}".format(DATASET))
    print()
    print("  SOLUTION :")
    print("    1. Aller sur roboflow.com")
    print("    2. Generate Dataset -> Export -> YOLOv8 -> Download ZIP")
    print("    3. Extraire dans : {}".format(DATASET))
    print()
    print("  Structure attendue :")
    print("    yolo_dataset/")
    print("      train/images/   train/labels/")
    print("      valid/images/   valid/labels/  (cree auto si absent)")
    print("      data.yaml")
    return None


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 2 — ENTRAINER YOLO
# ══════════════════════════════════════════════════════════════════════════

def entrainer(data_yaml: str) -> str:
    """Entraine YOLO et retourne le chemin du modele best.pt."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ERREUR : ultralytics non installe -> pip install ultralytics")
        return None

    print()
    print("  Demarrage entrainement...")
    print("  Modele : yolo11n.pt (nano, compatible CPU)")
    print("  Epochs : {}  Batch : {}  Imgsz : {}".format(EPOCHS, BATCH, IMGSZ))
    print()

    model = YOLO("yolo11n.pt")

    results = model.train(
        data      = data_yaml,
        epochs    = EPOCHS,
        imgsz     = IMGSZ,
        batch     = BATCH,
        project   = str(SAVE),
        name      = "yolo_cheque",
        patience  = 25,
        save      = True,
        plots     = True,
        verbose   = True,
        exist_ok  = True,
        # Augmentations valides pour YOLO
        degrees   = 5.0,     # rotation legere
        scale     = 0.15,    # zoom leger
        fliplr    = 0.0,     # pas de flip (cheques non symetriques)
        flipud    = 0.0,
        hsv_v     = 0.3,     # variation luminosite (remplace 'brightness')
        hsv_h     = 0.01,    # variation teinte
        hsv_s     = 0.3,     # variation saturation
    )

    best = SAVE / "yolo_cheque" / "weights" / "best.pt"
    if best.exists():
        print()
        print("  Modele sauvegarde : {}".format(best))
        return str(best)

    print("  ERREUR : best.pt non trouve")
    return None


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 3 — METRIQUES
# ══════════════════════════════════════════════════════════════════════════

def afficher_metriques(best_pt: str):
    from ultralytics import YOLO
    model   = YOLO(best_pt)
    metrics = model.val(verbose=False)
    print()
    print("  Metriques validation :")
    print("    mAP50    : {:.1f}%".format(metrics.box.map50 * 100))
    print("    mAP50-95 : {:.1f}%".format(metrics.box.map   * 100))
    print("    Precision: {:.1f}%".format(metrics.box.mp    * 100))
    print("    Recall   : {:.1f}%".format(metrics.box.mr    * 100))
    if metrics.box.map50 >= 0.70:
        print("  -> Bon modele (mAP50 >= 70%)")
    elif metrics.box.map50 >= 0.50:
        print("  -> Acceptable — ajouter plus d images pour ameliorer")
    else:
        print("  -> Faible — annoter 20+ images dans Roboflow")


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 4 — TEST VISUEL
# ══════════════════════════════════════════════════════════════════════════

def tester(best_pt: str):
    import cv2
    from ultralytics import YOLO

    model = YOLO(best_pt)

    img_path = None
    for sub in ["train/images", "valid/images", "images/train"]:
        imgs = list((DATASET / sub).glob("*.jpg")) + \
               list((DATASET / sub).glob("*.png"))
        if imgs:
            img_path = str(imgs[0])
            break

    if not img_path:
        print("  Aucune image de test trouvee")
        return

    print()
    print("  Test sur : {}".format(img_path))
    img = cv2.imread(img_path)
    res = model(img, conf=0.20, verbose=False)[0]
    print("  Zones detectees : {}".format(len(res.boxes)))

    for box in res.boxes:
        cls  = int(box.cls[0])
        conf = float(box.conf[0])
        nom  = CLASSES[cls] if cls < len(CLASSES) else "?"
        print("    [{:02d}] {:25s} conf={:.2f}".format(cls, nom, conf))

    out = ROOT / "debug_yolo_test.jpg"
    res.save(filename=str(out))
    print()
    print("  Image annotee sauvegardee : {}".format(out))
    print("  Ouvrir ce fichier pour verifier les detections visuellement")


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  ENTRAINEMENT YOLO — Zones cheque tunisien")
    print("=" * 60)
    print()
    print("  Classes ({}) :".format(len(CLASSES)))
    for i, c in enumerate(CLASSES):
        print("    {} : {}".format(i, c))

    print(); print("-" * 60); print("  ETAPE 1 — Dataset"); print("-" * 60)
    data_yaml = verifier_dataset()
    if not data_yaml:
        exit(1)

    print(); print("-" * 60); print("  ETAPE 2 — Entrainement"); print("-" * 60)
    best_pt = entrainer(data_yaml)
    if not best_pt:
        exit(1)

    print(); print("-" * 60); print("  ETAPE 3 — Metriques"); print("-" * 60)
    afficher_metriques(best_pt)

    print(); print("-" * 60); print("  ETAPE 4 — Test visuel"); print("-" * 60)
    tester(best_pt)

    print()
    print("=" * 60)
    print("  TERMINE")
    print()
    print("  Modele : {}".format(best_pt))
    print()
    print("  Tester avec :")
    print("  python test_ocr_solo.py cheque.jpg \\")
    print("         --yolo {}".format(best_pt))
    print("=" * 60)