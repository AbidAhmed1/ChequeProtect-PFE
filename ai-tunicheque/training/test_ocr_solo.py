"""
test_ocr_solo.py
=================
Test OCR standalone — YOLO + PaddleOCR v5.

FIX : PaddleOCR v5 utilise predict() au lieu de ocr()
      L'argument det=False n'existe plus en v5.

USAGE :
  cd D:\projet-pfe\ai-tunicheque
  python test_ocr_solo.py training\templates\template_07.jpg
  python test_ocr_solo.py training\templates\template_07.jpg --yolo saved_models\yolo_cheque\weights\best.pt
  python test_ocr_solo.py --test-regex
"""

import os
os.environ["FLAGS_use_mkldnn"]                      = "0"
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["GLOG_minloglevel"]                      = "3"

import sys, re, cv2, time, argparse
import numpy as np
import warnings
warnings.filterwarnings("ignore")

_PROJ        = os.path.dirname(os.path.abspath(__file__))
YOLO_DEFAULT = os.path.join(
    _PROJ, "saved_models", "yolo_cheque", "weights", "best.pt")

YOLO_CLASSES = {
    0:"montant_plafond", 1:"numero_cheque", 2:"rib_cmc7",
    3:"date", 4:"beneficiaire", 5:"montant_chiffres",
    6:"montant_lettres", 7:"signature",
}


# ══════════════════════════════════════════════════════════════════════════
#  PADDLE OCR — COMPATIBLE v4 ET v5
# ══════════════════════════════════════════════════════════════════════════

_paddle_instance = None
_paddle_version  = None  # "v4" ou "v5"


def _detecter_version_paddle():
    """Detecte si PaddleOCR v4 ou v5 est installé."""
    try:
        import paddleocr
        v = getattr(paddleocr, "__version__", "2.x")
        est_v5 = int(str(v).split(".")[0]) >= 3
        return "v5" if est_v5 else "v4", str(v)
    except Exception:
        return "v4", "inconnu"


def get_paddle():
    global _paddle_instance, _paddle_version
    if _paddle_instance is None:
        version, vstr = _detecter_version_paddle()
        _paddle_version = version
        try:
            from paddleocr import PaddleOCR
            if version == "v5":
                _paddle_instance = PaddleOCR(
                    use_textline_orientation=True, lang="fr")
                print("  PaddleOCR v5 ({}) : OK".format(vstr))
            else:
                _paddle_instance = PaddleOCR(
                    use_angle_cls=True, lang="fr")
                print("  PaddleOCR v4 ({}) : OK".format(vstr))
        except Exception as e:
            print("  PaddleOCR ERREUR : {}".format(e))
    return _paddle_instance, _paddle_version


def ocr_sur_numpy(img: np.ndarray) -> str:
    """
    Applique PaddleOCR sur un tableau numpy.
    Compatible v4 (ocr()) et v5 (predict()).
    """
    ocr, version = get_paddle()
    if ocr is None or img is None or img.size == 0:
        return ""
    try:
        if version == "v5":
            # PaddleOCR v5 : predict() retourne une liste de dicts
            results = ocr.predict(img)
            textes  = []
            if results:
                for item in results:
                    if isinstance(item, dict):
                        t = item.get("rec_text") or item.get("text", "")
                        if t: textes.append(str(t))
                    elif isinstance(item, list):
                        for sub in item:
                            if isinstance(sub, dict):
                                t = sub.get("rec_text") or sub.get("text","")
                                if t: textes.append(str(t))
                            elif isinstance(sub, (list, tuple)) and len(sub)>=2:
                                t = sub[1][0] if isinstance(sub[1],(list,tuple)) \
                                    else str(sub[1])
                                if t: textes.append(t)
            return " ".join(textes)
        else:
            # PaddleOCR v4 : ocr() retourne [[ligne1, ligne2, ...]]
            r = ocr.ocr(img, cls=True)
            if r and r[0]:
                return " ".join(str(l[1][0]) for l in r[0] if l)
            return ""
    except Exception as e:
        print("    [OCR ERREUR] : {}".format(e))
        return ""


def ocr_sur_crop(crop: np.ndarray) -> str:
    """OCR sur un crop avec zoom automatique si trop petit."""
    if crop is None or crop.size == 0:
        return ""
    h, w = crop.shape[:2]
    if w < 300 or h < 25:
        scale = max(300/max(w,1), 25/max(h,1), 2.0)
        crop  = cv2.resize(crop, (int(w*scale), int(h*scale)),
                           interpolation=cv2.INTER_CUBIC)
    crop = normaliser(crop)
    return ocr_sur_numpy(crop)


# ══════════════════════════════════════════════════════════════════════════
#  FONCTIONS D'EXTRACTION REGEX
# ══════════════════════════════════════════════════════════════════════════

def extraire_montant(texte: str):
    """Plafond — formats FR+AR. Max BCT = 30 000 DT."""
    t = re.sub(r'\s+', ' ', texte.lower().strip())
    patterns = [
        r'plafond[^0-9]{0,30}?(\d+(?:[,.]\d+)?)\s*d\.?t\.?',
        r'montant\s*max[a-z]*[^0-9]{0,20}?(\d+(?:[,.]\d+)?)',
        r'valeur\s*max[a-z]*[^0-9]{0,20}?(\d+(?:[,.]\d+)?)',
        r'd\.?t\.?\s*(\d+(?:[,.]\d+)?)',
        r'(\d+(?:[,.]\d+)?)\s{0,3}d\.?t\.?',
        r'(?:قيمة\s*القصوى|المبلغ\s*الاقصى)[^0-9]{0,15}?(\d+(?:[,.]\d+)?)',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            try:
                raw = m.group(1).strip()
                raw = raw.split()[0] if ' ' in raw else raw
                v   = float(re.sub(r'[\s]', '', raw).replace(',', '.'))
                if 10 <= v <= 30_000:
                    return v
            except ValueError:
                pass
    return None


def extraire_date(texte: str):
    """Date — formats FR+AR."""
    t = re.sub(r'\s+', ' ', texte.lower().strip())
    patterns = [
        r'date\s*(?:d\'?expir\w*|validit\w*)\s*:?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        r'valable\s*(?:jusqu\w*\s*[àa]?)?\s*[:\s]?\s*(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        r'(?:تاريخ\s*انتهاء)[^0-9]{0,20}(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})',
        r'\b(\d{2}[/\-\.]\d{2}[/\-\.]\d{4})\b',
        r'\b(\d{8})\b',
    ]
    for pat in patterns:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            d = m.group(1)
            if len(d) == 8 and d.isdigit():
                return "{}/{}/{}".format(d[0:2], d[2:4], d[4:8])
            return d.replace('-', '/').replace('.', '/').strip()
    return None


def extraire_rib(texte: str):
    """RIB — 20 chiffres avec contexte prioritaire."""
    t_compact = re.sub(r'\s', '', texte)
    t         = texte.lower()
    patterns  = [
        r'(?:titulaire\s*du\s*compte|صاحب\s*الحساب)[^0-9]{0,30}?(\d{20})',
        r'(?:rib|r\.i\.b\.?)\s*:?\s*(\d{20})',
        r'compte\s*n[o°]?\s*:?\s*(\d{20})',
        r'(\d{20})',
    ]
    for pat in patterns:
        m = re.search(pat, t_compact, re.IGNORECASE)
        if m: return m.group(1)
        m = re.search(pat, t, re.IGNORECASE)
        if m: return re.sub(r'\s', '', m.group(1))
    return None


def extraire_numero_cheque(texte: str):
    """N° chèque — 6-8 chiffres."""
    m = re.search(r'(?:ch[eè]que\s*[n°o]+\s*[:.]?\s*)(\d{6,8})',
                  texte, re.IGNORECASE)
    if m: return m.group(1)
    m = re.search(r'\b(\d{6,8})\b', texte)
    return m.group(1) if m else None


def normaliser(img: np.ndarray) -> np.ndarray:
    lum = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())
    if lum < 80:
        img = np.clip(img.astype(np.float32)*(150/max(lum,1)),0,255).astype(np.uint8)
    if lum < 160:
        lab   = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
        l,a,b = cv2.split(lab)
        l     = cv2.createCLAHE(2.5,(8,8)).apply(l)
        img   = cv2.cvtColor(cv2.merge([l,a,b]), cv2.COLOR_LAB2BGR)
    return img


def sep(t=""):
    if t: print("\n" + "─"*60 + "\n  " + t + "\n" + "─"*60)


# ══════════════════════════════════════════════════════════════════════════
#  TEST UNITAIRE REGEX
# ══════════════════════════════════════════════════════════════════════════

def test_fonctions_extraction():
    sep("TEST UNITAIRE DES FONCTIONS D'EXTRACTION")
    cas_m = [
        ("plafond du cheque : 5000dt",                   5000.0),
        ("Montant Max DT 5000 قيمة القصوى دت",           5000.0),
        ("Montant max : 2000dt",                         2000.0),
        ("Montant max DT 5000 wl B.R0#6S9P82Y# 4122752", 5000.0),
        ("Montant max DT s 000as1 BRD# 4122752",          None),
        ("4122752 cheque numero BT",                      None),
    ]
    cas_d = [
        ("date d'expiration 20/03/2026", "20/03/2026"),
        ("valable jusqu'a 27/03/2027",   "27/03/2027"),
        ("Le 19/09/2025 a Tunis",        "19/09/2025"),
        ("19092025",                      "19/09/2025"),
    ]
    cas_r = [
        ("titulaire du compte صاحب الحساب 05207000077307812272",
         "05207000077307812272"),
        ("RIB : 05207000077307812272", "05207000077307812272"),
        ("sacslall 4122752 bruit",     None),
    ]

    def tester(nom, cas, fn):
        ok = 0
        print("  {} :".format(nom))
        for texte, att in cas:
            res  = fn(texte)
            flag = res == att
            if flag: ok += 1
            print("    {} {:50s} → {}".format(
                "OK" if flag else "FAIL", texte[:50], res))
        print("    {}/{} OK\n".format(ok, len(cas)))
        return ok, len(cas)

    ok1,n1 = tester("Montant", cas_m, extraire_montant)
    ok2,n2 = tester("Date",    cas_d, extraire_date)
    ok3,n3 = tester("RIB",     cas_r, extraire_rib)
    print("  Score total : {}/{} OK".format(ok1+ok2+ok3, n1+n2+n3))


# ══════════════════════════════════════════════════════════════════════════
#  SECTION 1 — DIAGNOSTIC IMAGE
# ══════════════════════════════════════════════════════════════════════════

def diagnostic_image(img, chemin):
    sep("1. DIAGNOSTIC IMAGE")
    h, w  = img.shape[:2]
    gray  = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    lum   = float(gray.mean())
    blur  = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    ratio = round(w/h, 2)
    print("  Fichier    : {}".format(chemin))
    print("  Dimensions : {}x{} pixels".format(w, h))
    print("  Ratio W/H  : {} {}".format(ratio,
                                        "OK (cheque)" if 1.5<=ratio<=3.0 else "INHABITUEL"))
    print("  Luminosite : {:.1f} {}".format(lum,"OK" if lum>80 else "SOMBRE"))
    print("  Nettete    : {:.1f} {}".format(blur,"OK" if blur>50 else "FLOUE"))
    print("  Resolution : {}".format("OK" if w>=800 else "< 800px"))


# ══════════════════════════════════════════════════════════════════════════
#  SECTION 2 — QR CODE
# ══════════════════════════════════════════════════════════════════════════

def test_qr(image_bytes):
    sep("2. QR CODE pecc.tn")
    try:
        from pyzbar import pyzbar
        from pyzbar.pyzbar import ZBarSymbol
        arr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        h, w = img.shape[:2]
        for img_p in [img,
                      cv2.resize(img,(w*2,h*2),interpolation=cv2.INTER_CUBIC),
                      cv2.resize(img,(w*3,h*3),interpolation=cv2.INTER_CUBIC)]:
            dec = pyzbar.decode(img_p, symbols=[ZBarSymbol.QRCODE])
            if dec:
                raw = dec[0].data.decode("utf-8", errors="ignore")
                if "pecc.tn" in raw.lower():
                    p  = raw.strip().split("/")
                    qr = {
                        "is_pecc":       True,
                        "numero_cheque": p[2].strip() if len(p)>2 else None,
                        "rib":           p[3].strip() if len(p)>3 else None,
                        "date_emission": ("{}/{}/{}".format(
                            p[7][0:2],p[7][2:4],p[7][4:8])
                                          if len(p)>7 and len(p[7])==8 else None),
                        "montant": (float(int(p[6]))/1000
                                    if len(p)>6 and p[6].strip().isdigit()
                                    else None),
                    }
                    print("  QR pecc.tn : DETECTE OK")
                    print("  N cheque   : {}".format(qr["numero_cheque"]))
                    print("  RIB        : {}".format(qr["rib"]))
                    print("  Date       : {}".format(qr["date_emission"]))
                    print("  Montant    : {} DT".format(qr["montant"]))
                    return qr
    except ImportError:
        print("  pyzbar non installe")
    print("  QR : NON DETECTE")
    return {"is_pecc": False}


# ══════════════════════════════════════════════════════════════════════════
#  SECTION 3 — YOLO + OCR (zones correctes + PaddleOCR v4/v5)
# ══════════════════════════════════════════════════════════════════════════

def test_avec_yolo(img, yolo_path):
    sep("3. YOLO + OCR")
    try:
        from ultralytics import YOLO
    except ImportError:
        print("  ultralytics non installe"); return {}

    model   = YOLO(yolo_path)
    img_n   = normaliser(img.copy())
    results = model(img_n, conf=0.10, verbose=False)[0]

    print("  Modele : {}".format(yolo_path))
    print("  Zones detectees : {}".format(len(results.boxes)))

    if len(results.boxes) == 0:
        print("  Aucune zone detectee")
        return {}

    os.makedirs("debug_crops", exist_ok=True)
    champs_textes = {}

    for box in results.boxes:
        cls_id = int(box.cls[0])
        conf   = float(box.conf[0])
        nom    = YOLO_CLASSES.get(cls_id, "inconnu")
        xyxy   = box.xyxy[0].tolist()
        h, w   = img_n.shape[:2]
        pad    = 15
        crop   = img_n[
            max(0, int(xyxy[1])-pad):min(h, int(xyxy[3])+pad),
            max(0, int(xyxy[0])-pad):min(w, int(xyxy[2])+pad)
        ]
        if crop.size == 0: continue

        cv2.imwrite("debug_crops/{}.jpg".format(nom), crop)

        # Essayer aussi avec zoom x2 pour les petits crops
        texte = ocr_sur_crop(crop)
        if not texte:
            ch, cw = crop.shape[:2]
            crop2  = cv2.resize(crop, (cw*2, ch*2),
                                interpolation=cv2.INTER_CUBIC)
            texte  = ocr_sur_numpy(normaliser(crop2))

        print("\n  [{:02d}] {:20s} conf={:.2f}".format(cls_id, nom, conf))
        print("    OCR : '{}'".format(texte[:80]))
        champs_textes[nom] = texte

    # Extraire les valeurs
    result = {"numero_cheque":None,"rib":None,"date":None,"montant":None}
    result["numero_cheque"] = extraire_numero_cheque(
        champs_textes.get("numero_cheque",""))
    result["date"]    = extraire_date(
        champs_textes.get("date",""))
    result["montant"] = extraire_montant(
        champs_textes.get("montant_plafond",""))
    result["rib"]     = extraire_rib(
        re.sub(r'\s','', champs_textes.get("rib_cmc7","")))

    print()
    print("  Champs extraits (YOLO+OCR) :")
    for k, label in [("numero_cheque","N cheque"),
                     ("rib","RIB"),
                     ("date","Date"),
                     ("montant","Plafond DT")]:
        v = result.get(k)
        print("    {} {:15s} : {}".format(
            "OK" if v else "--", label, v or "NON EXTRAIT"))
    return {"champs": result, "source": "yolo+paddleocr"}


# ══════════════════════════════════════════════════════════════════════════
#  SECTION 3B — OCR IMAGE COMPLETE (fallback sans YOLO)
# ══════════════════════════════════════════════════════════════════════════

def test_ocr_complet(img):
    sep("3. OCR IMAGE COMPLETE (fallback)")
    img_n = normaliser(img.copy())
    h, w  = img_n.shape[:2]
    gray  = cv2.cvtColor(img_n, cv2.COLOR_BGR2GRAY)
    img_c = cv2.cvtColor(cv2.createCLAHE(2.0,(8,8)).apply(gray),
                         cv2.COLOR_GRAY2BGR)
    passes = [
        ("brute",         img_n),
        ("zoom_x2",       cv2.resize(img_n,(w*2,h*2),interpolation=cv2.INTER_CUBIC)),
        ("clahe",         img_c),
        ("zoom_x2+clahe", cv2.resize(img_c,(w*2,h*2),interpolation=cv2.INTER_CUBIC)),
    ]

    meilleur_n, meilleur_txt, meilleur_nom = 0, "", ""
    txt_montant, nom_montant = None, ""

    for nom, img_p in passes:
        try:
            t0  = time.time()
            txt = ocr_sur_numpy(img_p)
            n   = len(txt.split()) if txt else 0
            print("\n  {} : {} mots ({:.1f}s)".format(
                nom, n, time.time()-t0))
            if txt:
                print("    -> '{}'".format(txt[:80]))
            if n > meilleur_n:
                meilleur_n, meilleur_txt, meilleur_nom = n, txt, nom
            if txt_montant is None and extraire_montant(txt):
                txt_montant, nom_montant = txt, nom
        except Exception as e:
            print("  {} ERREUR : {}".format(nom, str(e)[:60]))

    if not meilleur_txt:
        print("\n  Aucun texte detecte")
        return {}

    txt_pour_montant = txt_montant or meilleur_txt
    champs = {
        "numero_cheque": extraire_numero_cheque(meilleur_txt),
        "rib":           extraire_rib(re.sub(r'\s','',meilleur_txt)),
        "date":          extraire_date(meilleur_txt),
        "montant":       extraire_montant(txt_pour_montant),
    }
    print("\n  Passe : {}".format(meilleur_nom))
    for k, label in [("numero_cheque","N cheque"),
                     ("rib","RIB"),("date","Date"),("montant","Plafond DT")]:
        v = champs.get(k)
        print("    {} {:15s} : {}".format(
            "OK" if v else "--", label, v or "NON EXTRAIT"))
    return {"champs": champs, "source": meilleur_nom}


# ══════════════════════════════════════════════════════════════════════════
#  RESUME FINAL
# ══════════════════════════════════════════════════════════════════════════

def afficher_resume(result, qr_data):
    sep("RESUME FINAL")
    champs = result.get("champs", {})
    source = result.get("source", "aucune")

    if not champs.get("rib") and qr_data.get("rib"):
        champs["rib"] = qr_data["rib"]
        print("  Info : RIB pris depuis QR (CMC7 illisible — normal)")

    print("  Source OCR : {}".format(source))
    print()

    if qr_data and qr_data.get("is_pecc"):
        ref = {"numero_cheque": qr_data.get("numero_cheque"),
               "rib":           qr_data.get("rib"),
               "date":          qr_data.get("date_emission"),
               "montant":       qr_data.get("montant")}
        print("  {:<20s}  {:<24s}  {:<24s}  {}".format(
            "Champ","QR (reference)","OCR (physique)","Resultat"))
        print("  " + "─"*76)
        for k, label in [("numero_cheque","N° cheque"),
                         ("rib","N° Compte (RIB)"),
                         ("date","Date"),
                         ("montant","Plafond DT")]:
            qv = str(ref.get(k,"—") or "—")
            ov = str(champs.get(k,"—") or "—")
            if qv!="—" and ov!="—":
                if k=="montant":
                    try: match="OK" if abs(float(qv)-float(ov))<1 else "FAIL"
                    except: match="?"
                else:
                    s1=re.sub(r'\s','',qv).upper()
                    s2=re.sub(r'\s','',ov).upper()
                    pct=sum(a==b for a,b in zip(s1,s2))/max(len(s1),len(s2))
                    match="OK" if pct>=0.9 else "PARTIEL {:.0%}".format(pct)
            elif ov=="—": match="OCR manquant"
            else:         match="QR manquant"
            print("  {:<20s}  {:<24s}  {:<24s}  {}".format(
                label, qv[:24], ov[:24], match))

    n = sum(1 for v in champs.values() if v is not None) if champs else 0
    print()
    print("  Score : {}/4 champs extraits".format(n))
    if n==4:   print("  -> Extraction complete OK")
    elif n==3: print("  -> Tres bon (3/4)")
    else:      print("  -> QR reste la source de verite")
    return champs


# ══════════════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?")
    parser.add_argument("--yolo", default=YOLO_DEFAULT)
    parser.add_argument("--test-regex", dest="test_regex",
                        action="store_true")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  TEST OCR SOLO — Cheque tunisien")
    print("=" * 60)

    if args.test_regex:
        test_fonctions_extraction()
        sys.exit(0)

    chemin = args.image
    if not chemin:
        chemin = next((f for f in os.listdir(".")
                       if f.lower().endswith((".jpg",".jpeg",".png",".bmp"))),
                      None)
    if not chemin or not os.path.exists(chemin):
        print("USAGE : python test_ocr_solo.py cheque.jpg")
        print("YOLO  : {}".format(YOLO_DEFAULT))
        print("Existe: {}".format(os.path.exists(YOLO_DEFAULT)))
        sys.exit(1)

    with open(chemin, "rb") as f:
        image_bytes = f.read()
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        print("Image illisible"); sys.exit(1)

    diagnostic_image(img, chemin)
    qr_data   = test_qr(image_bytes)
    yolo_path = os.path.normpath(args.yolo)
    yolo_ok   = os.path.exists(yolo_path)

    print("\n  Chemin YOLO : {}".format(yolo_path))
    print("  Existe      : {}".format(yolo_ok))

    if yolo_ok:
        result = test_avec_yolo(img, yolo_path)
    else:
        print("  -> Fallback OCR image complete")
        result = test_ocr_complet(img)

    afficher_resume(result, qr_data)
    print()