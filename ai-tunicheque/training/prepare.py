
"""
training/prepare_v3.py
=======================
Generation du dataset d entrainement v3 FINAL.

SOURCES :
  training\templates\                    vrais cheques banque (photos)
  data\cheques_dataset\real_scans\       vrais cheques scannes (NOUVEAU)
  data\fake_selectionnes\                faux documents reels

DATASET GENERE :
  data\cheques_dataset\real\             vrais augmentes
  data\cheques_dataset\fake\             faux augmentes

NOUVEAUTES vs version precedente :
  1. Lit depuis fake_selectionnes\ (pas fake_reels\)
  2. Integre les vrais scans avec augmentations douces
  3. Image originale du scan incluse telle quelle
"""

from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import numpy as np
import cv2
import random
import os
import io
import sys
import time
from pathlib import Path

# ── CHEMINS ────────────────────────────────────────────────────────────────
REAL_DIR     = Path(r"D:\projet-pfe\ai-tunicheque\training\templates")
REAL_SCANS = Path(r"D:\projet-pfe\ai-tunicheque\data\sources_real\real_scans")
FAKE_DIR     = Path(r"D:\projet-pfe\ai-tunicheque\data\fake_selectionnes")
DATASET_REAL = Path(r"D:\projet-pfe\ai-tunicheque\data\cheques_dataset\real")
DATASET_FAKE = Path(r"D:\projet-pfe\ai-tunicheque\data\cheques_dataset\fake")

# ── PARAMETRES ──────────────────────────────────────────────────────────────
AUG_MOBILE    = 40   # Variantes mobile par template
AUG_SCANNER   = 40   # Variantes scanner par template
AUG_SCAN_REEL = 15   # Variantes par vrai scan (moins agressif)
AUG_PAR_FAKE  = 5    # Augmentations par faux document


def _polices():
    for bp, rp in [("C:/Windows/Fonts/arialbd.ttf",
                    "C:/Windows/Fonts/arial.ttf")]:
        if os.path.exists(bp):
            try:
                return {"lg": ImageFont.truetype(bp, 22),
                        "sm": ImageFont.truetype(rp, 11)}
            except Exception:
                pass
    d = ImageFont.load_default()
    return {"lg": d, "sm": d}

_FF = _polices()


# ══════════════════════════════════════════════════════════════════════════
#  AUGMENTATIONS MOBILE
# ══════════════════════════════════════════════════════════════════════════

def mob_flou(img):
    return img.filter(ImageFilter.GaussianBlur(
        radius=random.uniform(0.5, 2.5)))

def mob_eclairage(img):
    img = ImageEnhance.Brightness(img).enhance(random.uniform(0.4, 1.7))
    return ImageEnhance.Contrast(img).enhance(random.uniform(0.6, 1.5))

def mob_perspective(img):
    arr = np.array(img)
    h, w = arr.shape[:2]
    ms = int(min(w, h) * 0.12)
    src = np.float32([[0,0],[w,0],[w,h],[0,h]])
    dst = np.float32([
        [random.randint(0,ms), random.randint(0,ms)],
        [w-random.randint(0,ms), random.randint(0,ms)],
        [w-random.randint(0,ms), h-random.randint(0,ms)],
        [random.randint(0,ms), h-random.randint(0,ms)],
    ])
    arr = cv2.warpPerspective(arr, cv2.getPerspectiveTransform(src, dst),
                              (w, h), borderValue=(255,255,255))
    return Image.fromarray(arr)

def mob_rotation(img):
    arr = np.array(img)
    h, w = arr.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), random.uniform(-15, 15), 1.0)
    return Image.fromarray(cv2.warpAffine(arr, M, (w,h),
                                          borderValue=(255,255,255)))

def mob_compression(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=random.randint(35, 70))
    buf.seek(0)
    return Image.open(buf).copy()

def mob_ombre(img):
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    s = random.choice(["g","d","h","b"])
    I = random.uniform(0.5, 0.85)
    L = random.randint(int(w*0.1), int(w*0.3))
    if s=="g": arr[:, :L]   *= I
    elif s=="d": arr[:, w-L:] *= I
    elif s=="h": arr[:L, :]   *= I
    else:        arr[h-L:, :] *= I
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

def mob_recadrage(img):
    w, h = img.size
    s = random.choice(["t","b","l","r"])
    c = random.uniform(0.02, 0.10)
    z = {"t":(0,int(h*c),w,h),"b":(0,0,w,int(h*(1-c))),
         "l":(int(w*c),0,w,h),"r":(0,0,int(w*(1-c)),h)}
    res = Image.new("RGB", (w,h), (255,255,255))
    res.paste(img.crop(z[s]), (0,0))
    return res

def mob_bruit(img):
    arr = np.array(img).astype(np.int16)
    return Image.fromarray(np.clip(
        arr + np.random.randint(-20, 20, arr.shape, dtype=np.int16),
        0, 255).astype(np.uint8))

def mob_saturation(img):
    return ImageEnhance.Color(img).enhance(random.uniform(0.3, 1.8))

AUG_MOB = [mob_flou, mob_eclairage, mob_perspective, mob_rotation,
           mob_compression, mob_ombre, mob_recadrage, mob_bruit, mob_saturation]


# ══════════════════════════════════════════════════════════════════════════
#  AUGMENTATIONS SCANNER
# ══════════════════════════════════════════════════════════════════════════

def scan_lum(img):
    return ImageEnhance.Brightness(img).enhance(random.uniform(0.80, 1.20))

def scan_cont(img):
    return ImageEnhance.Contrast(img).enhance(random.uniform(0.85, 1.40))

def scan_rot(img):
    arr = np.array(img)
    h, w = arr.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), random.uniform(-3, 3), 1.0)
    return Image.fromarray(cv2.warpAffine(arr, M, (w,h),
                                          borderValue=(255,255,255)))

def scan_res(img):
    w, h = img.size
    f = random.choice([0.5, 0.75, 1.0, 1.5])
    if f != 1.0:
        img = img.resize((max(int(w*f),100), max(int(h*f),50)),
                         Image.LANCZOS).resize((w,h), Image.LANCZOS)
    return img

def scan_gris(img):
    return img.convert("L").convert("RGB")

def scan_net(img):
    for _ in range(random.randint(1, 2)):
        img = img.filter(ImageFilter.SHARPEN)
    return img

def scan_comp(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=random.randint(70, 95))
    buf.seek(0)
    return Image.open(buf).copy()

def scan_pli(img):
    arr = np.array(img).astype(np.float32)
    h, w = arr.shape[:2]
    amp = random.uniform(0.995, 1.005)
    for c in range(w):
        off = int(amp * np.sin(c / (w/8) * np.pi))
        if 0 <= off < h:
            arr[:, c] = np.roll(arr[:, c], off, axis=0)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))

AUG_SCAN = [scan_lum, scan_cont, scan_rot, scan_res,
            scan_gris, scan_net, scan_comp, scan_pli]


# ══════════════════════════════════════════════════════════════════════════
#  AUGMENTATIONS DOUCES pour vrais scans
# ══════════════════════════════════════════════════════════════════════════

def scanreel_lum(img):
    return ImageEnhance.Brightness(img).enhance(random.uniform(0.60, 1.40))

def scanreel_cont(img):
    return ImageEnhance.Contrast(img).enhance(random.uniform(0.80, 1.30))

def scanreel_bruit(img):
    arr = np.array(img).astype(np.int16)
    return Image.fromarray(np.clip(
        arr + np.random.randint(-8, 8, arr.shape, dtype=np.int16),
        0, 255).astype(np.uint8))

def scanreel_rot(img):
    arr = np.array(img)
    h, w = arr.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), random.uniform(-2, 2), 1.0)
    return Image.fromarray(cv2.warpAffine(arr, M, (w,h),
                                          borderValue=(255,255,255)))

def scanreel_gris(img):
    return img.convert("L").convert("RGB")

def scanreel_comp(img):
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=random.randint(75, 98))
    buf.seek(0)
    return Image.open(buf).copy()

AUG_SCANREEL = [scanreel_lum, scanreel_cont, scanreel_bruit,
                scanreel_rot, scanreel_gris, scanreel_comp]


# ── Fonctions d application ───────────────────────────────────────────────

def appliquer(img, pool, n):
    r = img.copy()
    for t in random.sample(pool, min(n, len(pool))):
        try: r = t(r)
        except Exception: pass
    return r


# ══════════════════════════════════════════════════════════════════════════
#  FAUX SYNTHETIQUES
# ══════════════════════════════════════════════════════════════════════════

def make_fake():
    t = random.choice(["facture","recu","document","scan_partiel"])
    if t == "facture":
        img = Image.new("RGB", (1080,400),
                        tuple(random.randint(240,255) for _ in range(3)))
        d = ImageDraw.Draw(img)
        d.rectangle([0,0,1080,50], fill=(random.randint(20,70),)*3)
        d.text((20,12), "SOCIETE {}".format(
            random.choice(["STEG","SONEDE","TOPNET","OREDOO","ORANGE"])),
               fill=(255,255,255), font=_FF["lg"])
        for i in range(random.randint(6,12)):
            d.text((30, 60+i*27),
                   "Ref: {}  Montant: {} TND".format(
                       random.randint(10000,99999),
                       round(random.uniform(10,300),3)),
                   fill=(50,50,50), font=_FF["sm"])
        return img
    elif t == "recu":
        img = Image.new("RGB", (1080,400), (255,255,255))
        d = ImageDraw.Draw(img)
        d.rectangle([5,5,1075,395], outline=(0,0,0), width=2)
        d.text((30,15), "RECU N° {}".format(random.randint(1000,9999)),
               fill=(0,0,0), font=_FF["lg"])
        for i in range(random.randint(5,10)):
            d.text((30, 60+i*28),
                   "Article {}: {} TND".format(
                       i+1, round(random.uniform(5,200),3)),
                   fill=(30,30,30), font=_FF["sm"])
        return img
    elif t == "scan_partiel":
        img = Image.new("RGB", (1080,400), (252,250,245))
        d = ImageDraw.Draw(img)
        d.rectangle([3,3,1076,396], outline=(180,160,120), width=2)
        s = random.choice(["g","d","b"])
        if s=="g":   d.rectangle([0,0,486,400], fill=(255,255,255))
        elif s=="d": d.rectangle([594,0,1080,400], fill=(255,255,255))
        else:        d.rectangle([0,220,1080,400], fill=(255,255,255))
        return img
    else:
        img = Image.new("RGB", (1080,400), (248,248,248))
        d = ImageDraw.Draw(img)
        d.rectangle([20,20,1060,380], outline=(100,100,100), width=1)
        d.text((30,25), "REPUBLIQUE TUNISIENNE",
               fill=(30,30,30), font=_FF["lg"])
        for i in range(random.randint(6,12)):
            y = 68+i*22
            d.line([(30,y),(random.randint(320,918),y)],
                   fill=(80,80,80), width=1)
        return img


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

def main(dry_run=False):
    print()
    print("="*65)
    print("  DATASET PHASE 1 v3 FINAL")
    print("  templates + real_scans + fake_selectionnes")
    print("="*65)

    exts = {".jpg",".jpeg",".png",".bmp",".webp"}
    if not REAL_DIR.exists():
        print("  ERREUR : {} introuvable".format(REAL_DIR))
        return

    real_files = [f for f in REAL_DIR.iterdir() if f.suffix.lower() in exts]
    scan_files = ([f for f in REAL_SCANS.iterdir() if f.suffix.lower() in exts]
                  if REAL_SCANS.exists() else [])
    fake_files = ([f for f in FAKE_DIR.iterdir() if f.suffix.lower() in exts]
                  if FAKE_DIR.exists() else [])

    print()
    print("  REAL — templates\\ : {} fichiers".format(len(real_files)))
    for f in real_files:
        try:
            img = Image.open(f)
            print("    {:40s}  {}x{}".format(f.name[:40], *img.size))
        except Exception as e:
            print("    {} ERREUR: {}".format(f.name, e))

    print()
    print("  REAL — real_scans\\ : {} fichiers".format(len(scan_files)))
    for f in scan_files:
        try:
            img = Image.open(f)
            print("    {:40s}  {}x{}".format(f.name[:40], *img.size))
        except Exception as e:
            print("    {} ERREUR: {}".format(f.name, e))

    print()
    print("  FAKE — fake_selectionnes\\ : {} fichiers".format(len(fake_files)))
    for f in fake_files:
        print("    {}".format(f.name))

    total_real = (len(real_files)*(AUG_MOBILE+AUG_SCANNER)
                  + len(scan_files)*AUG_SCAN_REEL)
    total_fake_aug = len(fake_files)*AUG_PAR_FAKE
    n_fake_syn = max(0, total_real - total_fake_aug)

    print()
    print("  Plan :")
    print("    {} templates x ({} mob + {} scan) = {} REAL".format(
        len(real_files), AUG_MOBILE, AUG_SCANNER,
        len(real_files)*(AUG_MOBILE+AUG_SCANNER)))
    print("    {} scans x {}                     = {} REAL".format(
        len(scan_files), AUG_SCAN_REEL, len(scan_files)*AUG_SCAN_REEL))
    print("    TOTAL REAL                        = {}".format(total_real))
    print("    {} faux x {}                      = {} FAKE".format(
        len(fake_files), AUG_PAR_FAKE, total_fake_aug))
    print("    Synthetiques                      = {}".format(n_fake_syn))
    print("    TOTAL FAKE                        = {}".format(
        total_fake_aug+n_fake_syn))

    if dry_run:
        print()
        print("  [DRY-RUN] rien genere. Relancer sans --dry-run")
        return

    for d in [DATASET_REAL, DATASET_FAKE]:
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*"):
            f.unlink()

    start = time.time()
    errors = count_real = count_fake = 0

    # REAL — templates
    print()
    print("  Generation REAL templates...")
    for f in real_files:
        try: original = Image.open(f).convert("RGB")
        except Exception as e:
            print("    Erreur {}: {}".format(f.name, e)); continue
        base = f.stem[:15]
        for v in range(AUG_MOBILE):
            try:
                appliquer(original, AUG_MOB, random.randint(2,4)).save(
                    str(DATASET_REAL/"real_{}_mob_{:03d}.jpg".format(base,v)),
                    quality=random.randint(70,92))
                count_real += 1
            except Exception: errors += 1
        for v in range(AUG_SCANNER):
            try:
                appliquer(original, AUG_SCAN, random.randint(2,3)).save(
                    str(DATASET_REAL/"real_{}_scan_{:03d}.jpg".format(base,v)),
                    quality=random.randint(85,98))
                count_real += 1
            except Exception: errors += 1
        print("    {:30s}  +{} (total:{})".format(
            f.name[:30], AUG_MOBILE+AUG_SCANNER, count_real))

    # REAL — vrais scans
    if scan_files:
        print()
        print("  Generation REAL scans reels...")
        for f in scan_files:
            try: original = Image.open(f).convert("RGB")
            except Exception as e:
                print("    Erreur {}: {}".format(f.name, e)); continue
            base = f.stem[:15]
            original.save(str(DATASET_REAL/"real_{}_orig.jpg".format(base)),
                          quality=95)
            count_real += 1
            for v in range(AUG_SCAN_REEL-1):
                try:
                    appliquer(original, AUG_SCANREEL,
                              random.randint(1,2)).save(
                        str(DATASET_REAL/"real_{}_scanreel_{:03d}.jpg".format(
                            base,v)),
                        quality=random.randint(88,98))
                    count_real += 1
                except Exception: errors += 1
            print("    {:30s}  orig+{} variantes (total:{})".format(
                f.name[:30], AUG_SCAN_REEL-1, count_real))

    # FAKE — fake_selectionnes
    print()
    print("  Augmentation FAKE (fake_selectionnes)...")
    for f in fake_files:
        try: original = Image.open(f).convert("RGB")
        except Exception: continue
        original.save(str(DATASET_FAKE/"fake_orig_{:05d}.jpg".format(
            count_fake)), quality=90)
        count_fake += 1
        for v in range(AUG_PAR_FAKE-1):
            try:
                appliquer(original, AUG_MOB+AUG_SCAN,
                          random.randint(1,3)).save(
                    str(DATASET_FAKE/"fake_reel_{:05d}_{}.jpg".format(
                        count_fake,v)),
                    quality=85)
                count_fake += 1
            except Exception: errors += 1
    print("    {} faux augmentes".format(count_fake))

    # FAKE — synthetiques
    if n_fake_syn > 0:
        print()
        print("  Generation {} synthetiques...".format(n_fake_syn))
        for i in range(n_fake_syn):
            try:
                appliquer(make_fake(), AUG_MOB+AUG_SCAN, 2).save(
                    str(DATASET_FAKE/"fake_synth_{:05d}.jpg".format(i)),
                    quality=82)
                count_fake += 1
            except Exception: errors += 1
            if (i+1) % 100 == 0:
                print("    {}/{}...".format(i+1, n_fake_syn))

    elapsed = time.time()-start
    total_r = len(list(DATASET_REAL.glob("*.jpg")))
    total_f = len(list(DATASET_FAKE.glob("*")))
    ratio   = min(total_r,total_f)/max(total_r,total_f,1)

    print()
    print("="*65)
    print("  TERMINE en {:.1f}s ({:.1f} min)".format(elapsed,elapsed/60))
    print("  REAL  : {}  FAKE  : {}  Ratio : {:.3f} {}".format(
        total_r, total_f, ratio, "OK" if ratio>0.85 else "DESEQUILIBRE"))
    print("  Erreurs : {}".format(errors))
    print()
    print("  Prochaines etapes :")
    print("    1. python training\\"
          ".py")
    print("    2. python training\\train_xgboost.py")
    print("="*65)


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)