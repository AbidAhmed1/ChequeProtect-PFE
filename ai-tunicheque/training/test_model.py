import tensorflow as tf
import numpy as np
import cv2
from PIL import Image
from pathlib import Path
import json
import sys

MODEL_PATH         = Path(r"D:\projet-pfe\ai-tunicheque\saved_models\best_model_phaseA.h5")
CLASS_INDICES_PATH = Path(r"D:\projet-pfe\ai-tunicheque\saved_models\class_indices.json")

IMG_SIZE       = (224, 224)
THRESHOLD_REAL = 0.75
THRESHOLD_FAKE = 0.45
MIN_QR_SIZE    = 30
BLUR_MIN       = 15.0
RATIO_MIN      = 1.5
RATIO_MAX      = 4.5
WIDTH_MIN      = 400
HEIGHT_MIN     = 120

print("Chargement du modele...")
model = tf.keras.models.load_model(str(MODEL_PATH))

with open(str(CLASS_INDICES_PATH)) as f:
    class_indices = json.load(f)

real_label = class_indices.get("real", 1)
print("Modele charge  |  classes: {}".format(class_indices))


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 0 : CONTROLE QUALITE
# ══════════════════════════════════════════════════════════════════════════

def controle_qualite(image_path):
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return {"ok": False, "raison": "IMAGE_ILLISIBLE",
                "message": "Fichier illisible — verifier le chemin complet"}
    h, w  = img.shape
    ratio = float(w) / h if h > 0 else 0.0
    if not (RATIO_MIN <= ratio <= RATIO_MAX):
        return {"ok": False, "raison": "RATIO_INVALIDE",
                "message": "Ratio {:.2f} invalide (attendu {}-{})".format(
                    ratio, RATIO_MIN, RATIO_MAX)}
    if w < WIDTH_MIN or h < HEIGHT_MIN:
        return {"ok": False, "raison": "RESOLUTION_INSUFFISANTE",
                "message": "Resolution {}x{} insuffisante (min {}x{})".format(
                    w, h, WIDTH_MIN, HEIGHT_MIN)}
    blur = cv2.Laplacian(img, cv2.CV_64F).var()
    if blur < BLUR_MIN:
        return {"ok": False, "raison": "IMAGE_FLOUE",
                "blur_score": round(blur, 1),
                "message": "Image trop floue (score {:.1f}, minimum {})".format(
                    blur, BLUR_MIN)}
    if   blur > 200: qualite = "EXCELLENTE"
    elif blur > 100: qualite = "BONNE"
    elif blur > 50:  qualite = "CORRECTE"
    else:            qualite = "ACCEPTABLE"
    return {"ok": True, "blur_score": round(blur, 1),
            "qualite": qualite, "dim": "{}x{}".format(w, h)}


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 1A : PREDICTION ML
# ══════════════════════════════════════════════════════════════════════════

def predire_ml(image_path):
    img = Image.open(image_path).convert("RGB").resize(IMG_SIZE)
    arr = np.array(img).astype(np.float32) / 255.0
    arr = np.expand_dims(arr, axis=0)
    raw = float(model.predict(arr, verbose=0)[0][0])
    proba_real = raw if real_label == 1 else 1.0 - raw
    proba_fake = 1.0 - proba_real
    if   proba_real >= THRESHOLD_REAL: ml_decision = "REAL"
    elif proba_real <  THRESHOLD_FAKE: ml_decision = "FAKE"
    else:                               ml_decision = "INCERTAIN"
    return {
        "decision":   ml_decision,
        "proba_real": round(proba_real * 100, 1),
        "proba_fake": round(proba_fake * 100, 1),
        "score":      round(proba_real, 4),
    }


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 1B : DETECTION QR TUNICHEQUE
# ══════════════════════════════════════════════════════════════════════════

def detecter_qr(image_path):
    detector = cv2.QRCodeDetector()
    img      = cv2.imread(image_path, cv2.IMREAD_COLOR)
    if img is None:
        return {"found": False, "message": "Image non lisible"}
    img_gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def _check(img_c, nom):
        data, pts, _ = detector.detectAndDecode(img_c)
        if pts is not None and len(pts) > 0:
            p    = pts[0]
            size = (np.linalg.norm(p[0]-p[1]) + np.linalg.norm(p[1]-p[2])) / 2
            if size >= MIN_QR_SIZE:
                return {"found": True,
                        "message": "QR TuniCheque trouve (passe {}, taille {:.0f}px)".format(
                            nom, size)}
        return None

    r = _check(img, "originale")
    if r: return r
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enh   = cv2.cvtColor(clahe.apply(img_gray), cv2.COLOR_GRAY2BGR)
    r     = _check(enh, "CLAHE")
    if r: return r
    _, bw = cv2.threshold(img_gray, 0, 255,
                          cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    r = _check(cv2.cvtColor(bw, cv2.COLOR_GRAY2BGR), "binarisee")
    if r: return r
    return {"found": False,
            "message": "Aucun QR TuniCheque/SIBTEL - cheque avant 2025"}


# ══════════════════════════════════════════════════════════════════════════
#  ETAPE 2 : DECISION COMBINEE ML + QR
#
#  Les deux s'executent toujours en parallele.
#  La decision finale tient compte des deux resultats.
#
#  Tableau de decision :
#  ┌─────────────┬────────────┬────────────────────┐
#  │ ML          │ QR         │ Decision finale    │
#  ├─────────────┼────────────┼────────────────────┤
#  │ REAL        │ PRESENT    │ VALIDE             │
#  │ REAL        │ ABSENT     │ REJECTED_NO_QR     │
#  │ INCERTAIN   │ PRESENT    │ VALIDE             │
#  │ INCERTAIN   │ ABSENT     │ PENDING_REVIEW     │
#  │ FAKE        │ PRESENT    │ REJECTED_FAKE      │
#  │ FAKE        │ ABSENT     │ REJECTED_FAKE      │
#  └─────────────┴────────────┴────────────────────┘
# ══════════════════════════════════════════════════════════════════════════

def decision_combinee(ml, qr):
    if ml["decision"] == "FAKE":
        return {
            "finale":   "REJECTED_FAKE",
            "raison":   "Structure de cheque non reconnue par le ML",
            "explication": "ML={} FAKE  |  QR={}".format(
                ml["proba_fake"], "PRESENT" if qr["found"] else "ABSENT")
        }

    if ml["decision"] == "REAL" and qr["found"]:
        return {
            "finale":   "VALIDE",
            "raison":   "ML=REAL + QR TuniCheque present",
            "explication": "ML={} REAL  |  QR=PRESENT".format(ml["proba_real"])
        }

    if ml["decision"] == "REAL" and not qr["found"]:
        return {
            "finale":   "REJECTED_NO_QR",
            "raison":   "Structure correcte mais pas de QR TuniCheque",
            "explication": "ML={} REAL  |  QR=ABSENT — cheque avant 2025".format(
                ml["proba_real"])
        }

    if ml["decision"] == "INCERTAIN" and qr["found"]:
        return {
            "finale":   "VALIDE",
            "raison":   "QR TuniCheque present compense le ML incertain",
            "explication": "ML={} INCERTAIN  |  QR=PRESENT".format(ml["proba_real"])
        }

    if ml["decision"] == "INCERTAIN" and not qr["found"]:
        return {
            "finale":   "PENDING_REVIEW",
            "raison":   "ML incertain ET pas de QR TuniCheque",
            "explication": "ML={} INCERTAIN  |  QR=ABSENT".format(ml["proba_real"])
        }

    return {
        "finale":   "PENDING_REVIEW",
        "raison":   "Cas non determine",
        "explication": ""
    }


# ══════════════════════════════════════════════════════════════════════════
#  ANALYSE COMPLETE
# ══════════════════════════════════════════════════════════════════════════

def analyser(image_path):
    print()
    print("=" * 62)
    print("  Image : {}".format(image_path))
    print("=" * 62)

    # ── Etape 0 : qualite ────────────────────────────────────────────────
    qualite = controle_qualite(image_path)
    print("  Controle qualite :")
    print("    Resultat : {}".format("OK" if qualite["ok"] else "ECHEC"))
    print("    Message  : {}".format(
        qualite.get("message", qualite.get("qualite", ""))))

    if not qualite["ok"]:
        print()
        print("  DECISION FINALE : REJECTED_QUALITY")
        print("  Raison          : {}".format(qualite["raison"]))
        if qualite["raison"] == "IMAGE_ILLISIBLE":
            print()
            print("  CONSEIL : Verifier que le chemin est correct")
            print("    Exemple : python training/test_model.py \"D:\\images\\cheque.jpg\"")
        elif qualite["raison"] == "IMAGE_FLOUE":
            print()
            print("  CONSEIL : Scanner a 300 DPI minimum")
        print("=" * 62)
        return

    # ── Etape 1A + 1B : ML et QR en parallele ────────────────────────────
    print()
    print("  Analyse en cours (ML + QR simultanement)...")
    ml = predire_ml(image_path)
    qr = detecter_qr(image_path)

    print()
    print("  ML Phase 1 :")
    print("    Decision    : {}".format(ml["decision"]))
    print("    REAL        : {}%".format(ml["proba_real"]))
    print("    FAKE        : {}%".format(ml["proba_fake"]))

    print()
    print("  QR TuniCheque/SIBTEL :")
    print("    Trouve      : {}".format("OUI" if qr["found"] else "NON"))
    print("    Message     : {}".format(qr["message"]))

    # ── Etape 2 : decision combinee ───────────────────────────────────────
    decision = decision_combinee(ml, qr)

    print()
    print("  " + "─" * 58)
    print("  DECISION FINALE : {}".format(decision["finale"]))
    print("  Raison          : {}".format(decision["raison"]))
    print("  Detail          : {}".format(decision["explication"]))
    print("=" * 62)


# ══════════════════════════════════════════════════════════════════════════
#  LANCEMENT
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print()
        print("Usage : python training/test_model.py chemin/vers/image.jpg")
        print()
        print("IMPORTANT : utiliser le chemin complet")
        print("  Correct   : python training/test_model.py \"D:\\images\\cheque.jpg\"")
        print("  Correct   : python training/test_model.py \"training\\templates\\template_01.jpg\"")
        print("  Incorrect : python training/test_model.py \"chemin\\image.jpg\"")
    else:
        analyser(sys.argv[1])