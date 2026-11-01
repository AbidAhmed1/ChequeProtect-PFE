"""
training/train_xgboost.py
==========================
XGBoost v3 — GroupKFold + dataset corrigé.

DATASET CORRECT :
  REAL = tout chèque (nouveaux + anciens) → templates\ + real_scans\
  FAKE = non-chèques (factures, documents) → fake_selectionnes\

GROUPKFOLD :
  Évite le data leakage : les augmentations d'un même original
  restent dans le même fold → vraie mesure de généralisation.
  CV=57.9% avant → attendu 70-80% après correction dataset.
"""

import os, cv2, json, time, pickle, random
import numpy as np
from pathlib import Path

random.seed(42); np.random.seed(42)

DATASETS_REAL = [
    Path(r"D:\projet-pfe\ai-tunicheque\data\cheques_dataset\real"),
    Path(r"D:\projet-pfe\ai-tunicheque\data\sources_real\real_scans"),
]
DATASETS_FAKE = [
    Path(r"D:\projet-pfe\ai-tunicheque\data\cheques_dataset\fake"),
]
SAVE_DIR        = Path(r"D:\projet-pfe\ai-tunicheque\saved_models")
MAX_PAR_DOSSIER = 200
AUG_SCANS       = 15
SAVE_DIR.mkdir(exist_ok=True)

print(); print("="*65)
print("  XGBOOST v3 — GroupKFold + dataset corrigé")
print("="*65)

try:
    import xgboost as xgb
    print("  xgboost : OK ({})".format(xgb.__version__))
except ImportError:
    os.system("pip install xgboost scikit-learn --quiet")
    import xgboost as xgb

from sklearn.model_selection import GroupKFold, GroupShuffleSplit
from sklearn.metrics import accuracy_score, confusion_matrix
from sklearn.preprocessing import StandardScaler

import sys
_ROOT = Path(r"D:\projet-pfe\ai-tunicheque")
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))
from app.phases.cheque_feature_extractor import ChequeFeatureExtractor


def aug_scan(img, n):
    out = []
    h,w = img.shape[:2]
    for _ in range(n):
        a = img.copy().astype(np.float32)
        a = np.clip(a*np.random.uniform(0.55,1.45), 0,255)
        a = np.clip(a+np.random.normal(0,np.random.uniform(0,5),a.shape),0,255).astype(np.uint8)
        M = cv2.getRotationMatrix2D((w//2,h//2),np.random.uniform(-2.5,2.5),1.0)
        a = cv2.warpAffine(a,M,(w,h),borderMode=cv2.BORDER_REFLECT)
        _,buf = cv2.imencode(".jpg",a,[cv2.IMWRITE_JPEG_QUALITY,np.random.randint(68,99)])
        a = cv2.imdecode(buf,cv2.IMREAD_COLOR)
        _,buf2 = cv2.imencode(".jpg",a,[cv2.IMWRITE_JPEG_QUALITY,95])
        out.append(buf2.tobytes())
    return out


def extraire(dossier, label, ext, desc, g_off):
    exts    = {".jpg",".jpeg",".png",".bmp"}
    files   = [f for f in dossier.iterdir() if f.suffix.lower() in exts]
    is_scan = "scan" in dossier.name.lower()
    if not files:
        print("  VIDE : {}".format(dossier)); return [],[],[],g_off
    random.shuffle(files); files=files[:MAX_PAR_DOSSIER]
    n_exp = len(files)*AUG_SCANS if is_scan else len(files)
    print("\n  {} : {} fichiers → {} images{}".format(
        desc,len(files),n_exp," (aug×{})".format(AUG_SCANS) if is_scan else ""))
    X,y,g,gc,errors = [],[],[],g_off,0
    for i,f in enumerate(files):
        try:
            raw=open(f,"rb").read()
            if is_scan:
                arr=np.frombuffer(raw,np.uint8); img=cv2.imdecode(arr,cv2.IMREAD_COLOR)
                if img is None: errors+=1; continue
                for v in [raw]+aug_scan(img,AUG_SCANS-1):
                    X.append(ext.extract_as_vector(v)); y.append(label); g.append(gc)
            else:
                X.append(ext.extract_as_vector(raw)); y.append(label); g.append(gc)
            gc+=1
        except Exception: errors+=1
        if (i+1)%50==0: print("    {}/{}...".format(i+1,len(files)))
    print("    OK : {} features, {} err, {} groupes".format(len(X),errors,gc-g_off))
    return X,y,g,gc


t0  = time.time()
ex  = ChequeFeatureExtractor()
Xa,ya,ga = [],[],[]
g_offset = 0

for d in DATASETS_REAL:
    if d.exists():
        X,y,g,g_offset=extraire(d,1,ex,"REAL—{}".format(d.name),g_offset)
        if X: Xa.append(np.array(X,dtype=np.float32)); ya.append(np.array(y,dtype=np.int32)); ga.append(np.array(g,dtype=np.int32))
    else: print("  SKIP : {}".format(d))

for d in DATASETS_FAKE:
    if d.exists():
        X,y,g,g_offset=extraire(d,0,ex,"FAKE—{}".format(d.name),g_offset)
        if X: Xa.append(np.array(X,dtype=np.float32)); ya.append(np.array(y,dtype=np.int32)); ga.append(np.array(g,dtype=np.int32))
    else: print("  SKIP : {}".format(d))

X=np.vstack(Xa); y=np.concatenate(ya); g=np.concatenate(ga)
idx=np.random.permutation(len(X)); X,y,g=X[idx],y[idx],g[idx]
nr,nf=int(np.sum(y==1)),int(np.sum(y==0))
print("\n  Dataset : REAL={} FAKE={} Total={} Groupes={}".format(
    nr,nf,len(X),len(np.unique(g))))

# GroupShuffleSplit (pas de leakage dans le test set)
gss=GroupShuffleSplit(1,test_size=0.20,random_state=42)
tr,te=next(gss.split(X,y,groups=g))
Xtr,Xte=X[tr],X[te]; ytr,yte=y[tr],y[te]; gtr=g[tr]

sc=StandardScaler(); Xtr=sc.fit_transform(Xtr); Xte=sc.transform(Xte)
with open(str(SAVE_DIR/"xgboost_scaler.pkl"),"wb") as f: pickle.dump(sc,f)

print("\n"+"="*65)
print("  ENTRAINEMENT XGBoost")
print("="*65)

spw=nf/max(nr,1)
print("  scale_pos_weight : {:.3f}".format(spw))

m=xgb.XGBClassifier(
    n_estimators=300, max_depth=4, learning_rate=0.05,
    subsample=0.8, colsample_bytree=0.8,
    reg_alpha=0.1, reg_lambda=1.0, min_child_weight=3,
    scale_pos_weight=spw, objective="binary:logistic",
    eval_metric="auc", early_stopping_rounds=30,
    random_state=42, n_jobs=-1, verbosity=0,
)
m.fit(Xtr,ytr,eval_set=[(Xte,yte)],verbose=False)
print("  Best n_estimators : {}".format(m.best_iteration))

yp=m.predict(Xte); acc=accuracy_score(yte,yp)
cm=confusion_matrix(yte,yp)
tn,fp,fn,tp=cm.ravel() if cm.shape==(2,2) else (0,0,0,0)
pre=tp/max(tp+fp,1); rec=tp/max(tp+fn,1)
f1=2*pre*rec/max(pre+rec,1e-8)

print("\n  Matrice de confusion :")
print("              Prédit REAL  Prédit FAKE")
print("  Vrai REAL :     {:4d}         {:4d}".format(tp,fn))
print("  Vrai FAKE :     {:4d}         {:4d}".format(fp,tn))
print("\n  Accuracy:{:.1f}%  Precision:{:.1f}%  Recall:{:.1f}%  F1:{:.3f}".format(
    acc*100,pre*100,rec*100,f1))

names=ChequeFeatureExtractor.feature_names()
imps=m.feature_importances_
print("\n  Importance features :")
for i in np.argsort(imps)[::-1]:
    print("    {:25s} {:.3f}  {}".format(names[i],imps[i],"█"*int(imps[i]*40)))

print("\n"+"="*65)
print("  CROSS-VALIDATION GroupKFold (5 folds)")
print("="*65)

scv=StandardScaler(); Xcv=scv.fit_transform(X)
gkf=GroupKFold(5); cvs=[]
for fold,(tri,vai) in enumerate(gkf.split(Xcv,y,groups=g)):
    spw2=int(np.sum(y[tri]==0))/max(int(np.sum(y[tri]==1)),1)
    mf=xgb.XGBClassifier(n_estimators=m.best_iteration,max_depth=4,
                         learning_rate=0.05,subsample=0.8,colsample_bytree=0.8,
                         scale_pos_weight=spw2,objective="binary:logistic",
                         random_state=42,n_jobs=-1,verbosity=0)
    mf.fit(Xcv[tri],y[tri])
    a=accuracy_score(y[vai],mf.predict(Xcv[vai]))
    cvs.append(a)
    print("  Fold {} : {:.1f}%  (grp_train={} grp_val={})".format(
        fold+1,a*100,len(np.unique(g[tri])),len(np.unique(g[vai]))))

cva=np.array(cvs)
print("\n  CV GroupKFold : {:.1f}% ± {:.1f}%".format(cva.mean()*100,cva.std()*100))

if cva.mean()>0.75:   print("  → Bon — le modèle généralise ✓")
elif cva.mean()>0.65: print("  → Correct — enrichir le dataset FAKE")
else:                 print("  → Dataset insuffisant — ajouter plus de factures variées")

mp=str(SAVE_DIR/"xgboost_cheque.pkl")
with open(mp,"wb") as f: pickle.dump(m,f)
with open(str(SAVE_DIR/"config_xgboost.json"),"w") as f:
    json.dump({"modele":"XGBoost_v3","n_estimators":int(m.best_iteration),
               "features":names,"n_real":nr,"n_fake":nf,
               "accuracy":round(acc,4),"f1":round(f1,4),
               "cv_mean":round(float(cva.mean()),4),
               "cv_std":round(float(cva.std()),4)},f,indent=2)

print("\n"+"="*65)
print("  TERMINÉ en {:.1f}s".format(time.time()-t0))
print("  Test:{:.1f}%  CV GroupKFold:{:.1f}%±{:.1f}%".format(
    acc*100,cva.mean()*100,cva.std()*100))
print("  {}".format(mp))
print("="*65)