"""
training/augment_dataset.py
============================
Augmentation de donnees pour YOLO — Cheques tunisiens.

PROBLEME :
  Peu d'images reelles disponibles
  → Generer des variantes augmentees pour enrichir le dataset

PRINCIPE :
  Chaque image annotee → 15 variantes augmentees
  Les boites YOLO sont transformees automatiquement
  avec chaque variante geometrique

AUGMENTATIONS APPLIQUEES :
  Couleur    : luminosite, contraste, saturation, teinte
  Bruit      : gaussien, sel-poivre, flou
  Geometrie  : rotation legere, zoom, decalage
  Qualite    : compression JPEG, downscale-upscale
  Mobile     : simulation photo mobile (bruit + flou + angle)
  Scanner    : simulation scan (contraste fort + desaturation)

ATTENTION :
  Les boites YOLO sont en format normalise [0-1]
  Pour les transformations geometriques → recalculer les coords
  Pour les transformations couleur → boites identiques

USAGE :
  python training/augment_dataset.py

RESULTAT :
  Avant  : 11 images
  Apres  : 11 x 15 = 165 images
  → Reentrainer : python training/train_yolo.py
"""

import cv2, os, shutil, random, math
import numpy as np
from pathlib import Path

random.seed(42)
np.random.seed(42)

# ── Configuration ──────────────────────────────────────────────────────────
ROOT       = Path(r"D:\projet-pfe\ai-tunicheque")
DATASET    = ROOT / "training" / "yolo_dataset"
TRAIN_IMG  = DATASET / "train" / "images"
TRAIN_LBL  = DATASET / "train" / "labels"
VALID_IMG  = DATASET / "valid" / "images"
VALID_LBL  = DATASET / "valid" / "labels"

# Nombre de variantes par image originale
N_AUGMENTATIONS = 15

# Ratio val (sur les images originales uniquement, pas les augmentees)
RATIO_VAL = 0.25


# ══════════════════════════════════════════════════════════════════════════
#  LECTURE / ECRITURE LABELS YOLO
# ══════════════════════════════════════════════════════════════════════════

def lire_labels(label_path: Path) -> list:
    """
    Lit un fichier .txt YOLO.
    Format : class_id cx cy w h (tout en [0,1] normalise)
    Retourne : [(class_id, cx, cy, w, h), ...]
    """
    if not label_path.exists():
        return []
    labels = []
    with open(label_path) as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) == 5:
                try:
                    labels.append((
                        int(parts[0]),
                        float(parts[1]),
                        float(parts[2]),
                        float(parts[3]),
                        float(parts[4]),
                    ))
                except ValueError:
                    pass
    return labels


def ecrire_labels(label_path: Path, labels: list):
    """Ecrit un fichier .txt YOLO."""
    with open(label_path, "w") as f:
        for cls, cx, cy, w, h in labels:
            # Clamp [0,1]
            cx = max(0.001, min(0.999, cx))
            cy = max(0.001, min(0.999, cy))
            w  = max(0.001, min(0.999, w))
            h  = max(0.001, min(0.999, h))
            f.write("{} {:.6f} {:.6f} {:.6f} {:.6f}\n".format(
                cls, cx, cy, w, h))


def sauvegarder(img: np.ndarray, labels: list,
                img_out: Path, lbl_out: Path, qualite: int = 92):
    """Sauvegarde image + labels YOLO."""
    cv2.imwrite(str(img_out), img,
                [cv2.IMWRITE_JPEG_QUALITY, qualite])
    ecrire_labels(lbl_out, labels)


# ══════════════════════════════════════════════════════════════════════════
#  TRANSFORMATIONS COULEUR (boites inchangees)
# ══════════════════════════════════════════════════════════════════════════

def aug_luminosite(img: np.ndarray, facteur: float) -> np.ndarray:
    """Modifier la luminosite (facteur 0.5=sombre, 1.5=clair)."""
    return np.clip(img.astype(np.float32) * facteur, 0, 255).astype(np.uint8)


def aug_contraste(img: np.ndarray, alpha: float,
                  beta: float = 0) -> np.ndarray:
    """Modifier le contraste (alpha) et luminosite (beta)."""
    return np.clip(img.astype(np.float32) * alpha + beta, 0, 255).astype(np.uint8)


def aug_hsv(img: np.ndarray, dh: float = 0, ds: float = 1.0,
            dv: float = 1.0) -> np.ndarray:
    """Modifier teinte (dh), saturation (ds), valeur (dv) en HSV."""
    hsv       = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    hsv[:,:,0] = (hsv[:,:,0] + dh) % 180
    hsv[:,:,1]  = np.clip(hsv[:,:,1] * ds, 0, 255)
    hsv[:,:,2]  = np.clip(hsv[:,:,2] * dv, 0, 255)
    return cv2.cvtColor(hsv.astype(np.uint8), cv2.COLOR_HSV2BGR)


def aug_bruit_gaussien(img: np.ndarray, sigma: float) -> np.ndarray:
    """Ajouter du bruit gaussien (simulation photo mobile)."""
    bruit = np.random.normal(0, sigma, img.shape).astype(np.float32)
    return np.clip(img.astype(np.float32) + bruit, 0, 255).astype(np.uint8)


def aug_flou(img: np.ndarray, ksize: int) -> np.ndarray:
    """Flou gaussien (simulation mouvement ou defocus)."""
    k = ksize if ksize % 2 == 1 else ksize + 1
    return cv2.GaussianBlur(img, (k, k), 0)


def aug_sel_poivre(img: np.ndarray, ratio: float = 0.005) -> np.ndarray:
    """Bruit sel-et-poivre."""
    out  = img.copy()
    n    = int(img.size * ratio)
    # Sel (blanc)
    coords = [np.random.randint(0, i-1, n) for i in img.shape[:2]]
    out[coords[0], coords[1]] = 255
    # Poivre (noir)
    coords = [np.random.randint(0, i-1, n) for i in img.shape[:2]]
    out[coords[0], coords[1]] = 0
    return out


def aug_compression_jpeg(img: np.ndarray, qualite: int) -> np.ndarray:
    """Simuler une photo de mauvaise qualite JPEG."""
    _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, qualite])
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def aug_scanner(img: np.ndarray) -> np.ndarray:
    """Simuler un scan : desaturation + contraste + legere grille."""
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Ameliorer le contraste comme un scanner
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)
    # Reconvertir en BGR
    img_s = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    # Legere variation de luminosite
    img_s = aug_luminosite(img_s, random.uniform(0.85, 1.15))
    return img_s


# ══════════════════════════════════════════════════════════════════════════
#  TRANSFORMATIONS GEOMETRIQUES (boites transformees)
# ══════════════════════════════════════════════════════════════════════════

def bbox_yolo_to_pixels(cx, cy, w, h, W, H):
    """YOLO [0-1] → pixels absolus (x1,y1,x2,y2)."""
    x1 = (cx - w/2) * W
    y1 = (cy - h/2) * H
    x2 = (cx + w/2) * W
    y2 = (cy + h/2) * H
    return x1, y1, x2, y2


def bbox_pixels_to_yolo(x1, y1, x2, y2, W, H):
    """Pixels absolus → YOLO [0-1]."""
    cx = (x1 + x2) / 2 / W
    cy = (y1 + y2) / 2 / H
    w  = (x2 - x1) / W
    h  = (y2 - y1) / H
    return cx, cy, w, h


def aug_rotation(img: np.ndarray, labels: list,
                 angle: float) -> tuple:
    """
    Rotation légère de l'image et transformation des boites.
    """
    H, W   = img.shape[:2]
    cx, cy = W / 2, H / 2
    M      = cv2.getRotationMatrix2D((cx, cy), angle, 1.0)
    img_r  = cv2.warpAffine(img, M, (W, H),
                            flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_REFLECT_101)
    new_labels = []
    for cls, bcx, bcy, bw, bh in labels:
        # 1. Convertir YOLO en pixels (x1, y1, x2, y2)
        x1, y1, x2, y2 = bbox_yolo_to_pixels(bcx, bcy, bw, bh, W, H)

        # 2. Préparer les 4 coins de la boîte [x, y]
        # On crée une matrice (3, 4) pour multiplier par la matrice de rotation M (2, 3)
        corners = np.array([
            [x1, x2, x2, x1],
            [y1, y1, y2, y2],
            [1,  1,  1,  1 ]
        ], dtype=np.float32)

        # 3. Appliquer la rotation aux coins : (2,3) @ (3,4) = (2,4)
        corners_rot = M @ corners
        xs, ys      = corners_rot[0], corners_rot[1]

        # 4. Recalculer la nouvelle boîte englobante (Bounding Box droite)
        nx1, nx2  = max(0, xs.min()), min(W, xs.max())
        ny1, ny2  = max(0, ys.min()), min(H, ys.max())

        # 5. Re-convertir en format YOLO
        if nx2 > nx1 and ny2 > ny1:
            ncx, ncy, nw, nh = bbox_pixels_to_yolo(nx1, ny1, nx2, ny2, W, H)
            new_labels.append((cls, ncx, ncy, nw, nh))

    return img_r, new_labels


def aug_zoom(img: np.ndarray, labels: list,
             facteur: float) -> tuple:
    """
    Zoom in (facteur > 1) ou zoom out (facteur < 1).
    Les boites sont redimensionnees.
    """
    H, W  = img.shape[:2]
    nW    = int(W * facteur)
    nH    = int(H * facteur)
    img_z = cv2.resize(img, (nW, nH), interpolation=cv2.INTER_LINEAR)

    if facteur > 1:
        # Zoom in → crop au centre
        x_off = (nW - W) // 2
        y_off = (nH - H) // 2
        img_z = img_z[y_off:y_off+H, x_off:x_off+W]
        # Transformer les boites
        new_labels = []
        for cls, cx, cy, bw, bh in labels:
            ncx = (cx * nW - x_off) / W
            ncy = (cy * nH - y_off) / H
            nw  = bw * nW / W
            nh  = bh * nH / H
            if 0 < ncx < 1 and 0 < ncy < 1:
                new_labels.append((cls, ncx, ncy,
                                   min(nw,0.99), min(nh,0.99)))
    else:
        # Zoom out → padding
        img_out = np.full((H, W, 3), 240, dtype=np.uint8)
        x_off   = (W - nW) // 2
        y_off   = (H - nH) // 2
        img_out[y_off:y_off+nH, x_off:x_off+nW] = img_z
        img_z   = img_out
        new_labels = []
        for cls, cx, cy, bw, bh in labels:
            ncx = (cx * nW + x_off) / W
            ncy = (cy * nH + y_off) / H
            nw  = bw * nW / W
            nh  = bh * nH / H
            new_labels.append((cls, ncx, ncy, nw, nh))

    return img_z, new_labels


def aug_decalage(img: np.ndarray, labels: list,
                 dx_ratio: float, dy_ratio: float) -> tuple:
    """Decalage horizontal et vertical de l'image."""
    H, W  = img.shape[:2]
    dx    = int(dx_ratio * W)
    dy    = int(dy_ratio * H)
    M     = np.float32([[1, 0, dx], [0, 1, dy]])
    img_t = cv2.warpAffine(img, M, (W, H),
                           borderMode=cv2.BORDER_REFLECT_101)
    new_labels = []
    for cls, cx, cy, bw, bh in labels:
        ncx = cx + dx_ratio
        ncy = cy + dy_ratio
        if 0.01 < ncx < 0.99 and 0.01 < ncy < 0.99:
            new_labels.append((cls, ncx, ncy, bw, bh))
    return img_t, new_labels


def aug_perspective(img: np.ndarray, labels: list,
                    force: float = 0.04) -> tuple:
    """
    Transformation de perspective legere
    (simule une photo prise de biais).
    """
    H, W = img.shape[:2]
    d    = force
    src  = np.float32([[0,0],[W,0],[W,H],[0,H]])
    dst  = np.float32([
        [W*random.uniform(0, d),     H*random.uniform(0, d)],
        [W*(1-random.uniform(0, d)), H*random.uniform(0, d)],
        [W*(1-random.uniform(0, d)), H*(1-random.uniform(0, d))],
        [W*random.uniform(0, d),     H*(1-random.uniform(0, d))],
    ])
    M     = cv2.getPerspectiveTransform(src, dst)
    img_p = cv2.warpPerspective(img, M, (W, H),
                                borderMode=cv2.BORDER_REFLECT_101)
    # Pour la perspective, garder les boites inchangees (approximation)
    # (la transformation est suffisamment legere)
    return img_p, labels


# ══════════════════════════════════════════════════════════════════════════
#  LISTE DES 15 AUGMENTATIONS
# ══════════════════════════════════════════════════════════════════════════

def generer_variantes(img: np.ndarray, labels: list) -> list:
    """
    Genere 15 variantes d'une image avec ses annotations.
    Retourne : [(img_augmentee, labels_augmentes, suffix_nom), ...]
    """
    variantes = []

    # ── Couleur (boites identiques) ───────────────────────────────────────

    # 1. Luminosite faible (photo sombre)
    variantes.append((
        aug_luminosite(img, 0.60), labels, "lum_bas"))

    # 2. Luminosite haute (photo surexposee)
    variantes.append((
        aug_luminosite(img, 1.40), labels, "lum_haut"))

    # 3. Contraste fort
    variantes.append((
        aug_contraste(img, alpha=1.5, beta=-30), labels, "contraste_fort"))

    # 4. Contraste faible
    variantes.append((
        aug_contraste(img, alpha=0.7, beta=20), labels, "contraste_faible"))

    # 5. Variation couleur (teinte legere)
    variantes.append((
        aug_hsv(img, dh=5, ds=0.9, dv=1.1), labels, "couleur"))

    # 6. Bruit gaussien (photo mobile grain)
    variantes.append((
        aug_bruit_gaussien(img, sigma=12), labels, "bruit_12"))

    # 7. Bruit fort (photo mauvaise qualite)
    variantes.append((
        aug_bruit_gaussien(img, sigma=25), labels, "bruit_25"))

    # 8. Flou leger (mise au point)
    variantes.append((
        aug_flou(img, ksize=3), labels, "flou_3"))

    # 9. Compression JPEG faible (photo compressée)
    variantes.append((
        aug_compression_jpeg(img, qualite=45), labels, "jpeg_45"))

    # 10. Simulation scanner
    variantes.append((
        aug_scanner(img), labels, "scanner"))

    # ── Geometrie (boites transformees) ───────────────────────────────────

    # 11. Rotation +3 degres
    img_r, lbl_r = aug_rotation(img, labels, angle=3.0)
    variantes.append((img_r, lbl_r, "rot_p3"))

    # 12. Rotation -3 degres
    img_r, lbl_r = aug_rotation(img, labels, angle=-3.0)
    variantes.append((img_r, lbl_r, "rot_m3"))

    # 13. Zoom in 15%
    img_z, lbl_z = aug_zoom(img, labels, facteur=1.15)
    variantes.append((img_z, lbl_z, "zoom_in"))

    # 14. Decalage droite+bas
    img_d, lbl_d = aug_decalage(img, labels, dx_ratio=0.05, dy_ratio=0.04)
    variantes.append((img_d, lbl_d, "decalage"))

    # 15. Perspective legere
    img_p, lbl_p = aug_perspective(img, labels, force=0.03)
    variantes.append((img_p, lbl_p, "perspective"))

    return variantes


# ══════════════════════════════════════════════════════════════════════════
#  PIPELINE PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════

def augmenter_dataset():
    """
    Lit toutes les images annotees dans train/images/
    et genere N_AUGMENTATIONS variantes pour chacune.
    """
    # Trouver les images originales
    exts = {".jpg", ".jpeg", ".png", ".bmp"}
    imgs = [f for f in TRAIN_IMG.glob("*") if f.suffix.lower() in exts]

    if not imgs:
        print("  ERREUR : Aucune image dans {}".format(TRAIN_IMG))
        return

    print("  Images originales    : {}".format(len(imgs)))
    print("  Variantes / image    : {}".format(N_AUGMENTATIONS))
    print("  Images totales apres : {}".format(
        len(imgs) * (1 + N_AUGMENTATIONS)))
    print()

    n_ok      = 0
    n_skip    = 0
    n_labels  = 0

    for i, img_path in enumerate(imgs):
        lbl_path = TRAIN_LBL / (img_path.stem + ".txt")

        # Charger image et labels
        img    = cv2.imread(str(img_path))
        labels = lire_labels(lbl_path)

        if img is None:
            print("  SKIP (illisible) : {}".format(img_path.name))
            n_skip += 1
            continue

        if not labels:
            print("  SKIP (pas de labels) : {}".format(img_path.name))
            n_skip += 1
            continue

        # Generer les variantes
        variantes = generer_variantes(img, labels)

        for img_aug, lbl_aug, suffix in variantes:
            # Nom de sortie : original_stem + _ + suffix
            nom_out  = "{}_aug_{}.jpg".format(img_path.stem, suffix)
            img_out  = TRAIN_IMG / nom_out
            lbl_out  = TRAIN_LBL / "{}_aug_{}.txt".format(
                img_path.stem, suffix)

            # Ne pas ecraser si deja existe
            if img_out.exists():
                continue

            if lbl_aug:  # Ne sauvegarder que si on a des boites valides
                sauvegarder(img_aug, lbl_aug, img_out, lbl_out)
                n_ok    += 1
                n_labels += len(lbl_aug)

        print("  [{:2d}/{}] {} → {} variantes".format(
            i+1, len(imgs), img_path.name[:40], len(variantes)))

    print()
    print("  Images augmentees creees : {}".format(n_ok))
    print("  Images skipees           : {}".format(n_skip))
    print("  Boites totales           : {}".format(n_labels))


# ══════════════════════════════════════════════════════════════════════════
#  CREER LE SPLIT VALIDATION (sur originaux uniquement)
# ══════════════════════════════════════════════════════════════════════════

def reconstruire_validation():
    """
    Recrée le dossier valid/ depuis les images ORIGINALES uniquement.
    Les images augmentees restent dans train/.
    Important : valid doit avoir des images originales
    pour une evaluation realiste.
    """
    # Supprimer l'ancien valid
    if VALID_IMG.exists():
        shutil.rmtree(VALID_IMG)
    if VALID_LBL.exists():
        shutil.rmtree(VALID_LBL)
    VALID_IMG.mkdir(parents=True)
    VALID_LBL.mkdir(parents=True)

    # Trouver uniquement les originaux (sans '_aug_' dans le nom)
    exts     = {".jpg", ".jpeg", ".png"}
    originaux = [f for f in TRAIN_IMG.glob("*")
                 if f.suffix.lower() in exts and "_aug_" not in f.name]

    if not originaux:
        print("  ERREUR : Aucun original trouve")
        return

    random.shuffle(originaux)
    n_val    = max(2, int(len(originaux) * RATIO_VAL))
    val_imgs = originaux[:n_val]

    for img_path in val_imgs:
        lbl_path = TRAIN_LBL / (img_path.stem + ".txt")
        shutil.copy2(img_path, VALID_IMG / img_path.name)
        if lbl_path.exists():
            shutil.copy2(lbl_path, VALID_LBL / lbl_path.name)

    print("  Valid reconstruit : {} images (originaux)".format(n_val))
    print("  Train total       : {} images (orig + aug)".format(
        len(list(TRAIN_IMG.glob("*.jpg")))))


# ══════════════════════════════════════════════════════════════════════════
#  STATISTIQUES
# ══════════════════════════════════════════════════════════════════════════

def afficher_stats():
    """Affiche les statistiques du dataset apres augmentation."""
    n_train = len([f for f in TRAIN_IMG.glob("*")
                   if f.suffix.lower() in {".jpg",".png"}])
    n_valid = len([f for f in VALID_IMG.glob("*")
                   if f.suffix.lower() in {".jpg",".png"}])
    n_orig  = len([f for f in TRAIN_IMG.glob("*")
                   if "_aug_" not in f.name and
                   f.suffix.lower() in {".jpg",".png"}])
    n_aug   = n_train - n_orig

    # Compter les boites par classe
    from collections import defaultdict
    classes_count = defaultdict(int)
    for lbl_f in TRAIN_LBL.glob("*.txt"):
        for cls, *_ in lire_labels(lbl_f):
            classes_count[cls] += 1

    print()
    print("  Dataset apres augmentation :")
    print("    Train : {} images ({} orig + {} aug)".format(
        n_train, n_orig, n_aug))
    print("    Valid : {} images (originaux)".format(n_valid))
    print()
    print("  Boites par classe (train) :")
    noms = ["montant_plafond","numero_cheque","rib_cmc7","date",
            "beneficiaire","montant_chiffres","montant_lettres","signature"]
    for cls_id in sorted(classes_count.keys()):
        nom = noms[cls_id] if cls_id < len(noms) else "?"
        print("    {:02d} {:20s} : {} boites".format(
            cls_id, nom, classes_count[cls_id]))


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("=" * 60)
    print("  AUGMENTATION DATASET YOLO — Cheques tunisiens")
    print("=" * 60)

    # Verifier les dossiers
    if not TRAIN_IMG.exists():
        print("  ERREUR : {} non trouve".format(TRAIN_IMG))
        exit(1)

    print()
    print("-" * 60)
    print("  ETAPE 1 — Augmentation ({} variantes/image)".format(
        N_AUGMENTATIONS))
    print("-" * 60)
    augmenter_dataset()

    print()
    print("-" * 60)
    print("  ETAPE 2 — Reconstruction validation")
    print("-" * 60)
    reconstruire_validation()

    print()
    print("-" * 60)
    print("  ETAPE 3 — Statistiques")
    print("-" * 60)
    afficher_stats()

    print()
    print("=" * 60)
    print("  AUGMENTATION TERMINEE")
    print()
    print("  Reentrainer YOLO maintenant :")
    print("  python training\\train_yolo.py")
    print("=" * 60)