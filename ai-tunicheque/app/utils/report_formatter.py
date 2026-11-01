"""
app/utils/report_formatter.py
──────────────────────────────
Formatter partagé pour afficher les résultats du pipeline TuniCheque.

Utilisé par :
  - app/main.py           → log console à la fin de chaque requête
  - tests/full_pipeline_test.py → affichage pour le développeur

Principe : un seul endroit où on définit le format → DRY.
"""
from typing import Dict, Any


# ══════════════════════════════════════════════════════════════════
#  ICÔNES D'ÉTAT (3 niveaux)
# ══════════════════════════════════════════════════════════════════
def phase_icon(p: Dict[str, Any]) -> str:
    """✅ validé | ⚠️ revue manuelle | ❌ rejeté | ⛔ erreur"""
    if not p:
        return "⛔"
    details = p.get("details", {})
    d = str(details.get("decision", "")).upper()
    if d == "ERROR" or "error" in details:
        return "⛔"
    if d.startswith("REJECTED"):
        return "❌"
    if d.startswith("PENDING") or d == "REVIEW":
        return "⚠️ "
    if p.get("passed") or d in ("COMPLIANCE_OK", "VALID_CHEQUE", "APPROVED"):
        return "✅"
    return "⚠️ "


def decision_icon(d: str) -> str:
    d = str(d).upper()
    if d == "APPROVED":
        return "✅"
    if d.startswith("REJECTED"):
        return "❌"
    if d.startswith("PENDING") or d == "REVIEW":
        return "⚠️ "
    return "⛔"


def check(ok: bool) -> str:
    return "✅" if ok else "❌"


# ══════════════════════════════════════════════════════════════════
#  PHASE 1 — Identification ML
# ══════════════════════════════════════════════════════════════════
def format_phase1(p: Dict[str, Any]) -> str:
    details = p.get("details", {})
    lines = []
    lines.append(f"Phase 1 — IDENTIFICATION   : {phase_icon(p)} "
                 f"({p.get('duration_ms', 0)} ms)")
    lines.append(f"   Décision : {details.get('decision', 'N/A')}")

    ml = details.get("ml", {}) or {}
    vote = ml.get("vote", {}) or {}
    lines.append(f"   Analyse ML :")
    lines.append(f"     CNN (réseau de neurones)  : "
                 f"{round(ml.get('cnn_score', 0), 4)}")
    lines.append(f"     XGBoost (features image)  : "
                 f"{round(ml.get('xgb_score', 0), 4)}")
    lines.append(f"     Vote final                : "
                 f"{vote.get('decision', 'N/A')} "
                 f"(score {round(vote.get('score_final', 0), 4)})")

    pd = details.get("print_detection")
    if pd:
        lines.append(f"   Détection impression      : "
                     f"{pd.get('decision', '—')} "
                     f"(confiance {pd.get('confidence', 0)})")

    qr = details.get("qr_code", {}) or {}
    found = qr.get("found", False)
    lines.append(f"   QR pecc.tn détecté        : {check(found)} "
                 f"{'oui' if found else 'non (Phase 2 prend le relais)'}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  PHASE 2 — Conformité QR (format détaillé)
# ══════════════════════════════════════════════════════════════════
def format_phase2(p: Dict[str, Any]) -> str:
    details = p.get("details", {})
    lines = []
    lines.append(f"Phase 2 — CONFORMITÉ QR    : {phase_icon(p)} "
                 f"({p.get('duration_ms', 0)} ms)")
    lines.append(f"   Décision : {details.get('decision', 'N/A')}")
    lines.append(f"   Score    : {round(p.get('score', 0), 4)}")
    lines.append("")

    # Vérifications BCT
    checks = details.get("checks", {}) or {}
    if checks:
        nb_ok = sum(1 for v in checks.values() if v)
        lines.append(f"   ┌─ VÉRIFICATIONS BCT ({nb_ok}/{len(checks)} OK)")
        noms = {
            "qr_lisible":        "QR code lisible",
            "rib_valide":        "RIB valide (format + Luhn)",
            "banque_valide":     "Banque reconnue",
            "date_valide":       "Date de validité OK",
            "montant_valide":    "Montant dans le plafond",
            "numero_present":    "Numéro de chèque présent",
            "qr_vs_physique_ok": "QR correspond au chèque",
        }
        for k, v in checks.items():
            lines.append(f"   │  {check(v)} {noms.get(k, k)}")
        lines.append("   │")

    # Données QR pecc.tn
    qr = details.get("qr_data") or {}
    if qr and isinstance(qr, dict):
        lines.append(f"   ┌─ DONNÉES QR pecc.tn")
        mapping = [
            ("numero_cheque", "N° chèque     "),
            ("rib",           "RIB           "),
            ("beneficiaire",  "Tireur        "),
            ("montant",       "Plafond       "),
            ("date_emission", "Validité      "),
            ("code_banque",   "Code banque   "),
        ]
        for k, label in mapping:
            v = qr.get(k)
            if v not in (None, ""):
                if k == "montant":
                    v = f"{v} DT"
                lines.append(f"   │  {label}: {v}")
        lines.append("   │")

    # Comparaison QR vs Physique
    comp = details.get("comparaison_qr_vs_physique") or {}
    tableau = comp.get("tableau", [])
    if tableau:
        lines.append(f"   ┌─ COMPARAISON QR vs CHÈQUE PHYSIQUE")
        for l in tableau:
            champ = l.get("champ", "").ljust(26)
            status = l.get("status", "—")
            qr_v = str(l.get("qr", ""))[:22]
            ocr_v = str(l.get("ocr", ""))[:22]
            det = l.get("detail", "")
            if status == "OK":
                ico = "✅"
            elif "WARN" in status:
                ico = "⚠️ "
            else:
                ico = "❌"
            lines.append(f"   │  {ico} {champ} {det}")
            if qr_v != ocr_v and qr_v and ocr_v and ocr_v != "—":
                lines.append(f"   │       QR  : {qr_v}")
                lines.append(f"   │       OCR : {ocr_v}")
        lines.append("   │")

    # Délai de validité
    delai = details.get("delai_info") or {}
    if delai:
        lines.append(f"   ┌─ DÉLAI DE VALIDITÉ")
        de = delai.get("date_expiration") or delai.get("date_limite") or "—"
        lines.append(f"   │  Expiration     : {de}")
        if delai.get("jours_restants") is not None:
            lines.append(f"   │  Jours restants : {delai['jours_restants']}")
        if delai.get("ok"):
            lines.append(f"   │  Statut         : ✅ valide")
        else:
            lines.append(f"   │  Statut         : ❌ "
                         f"{delai.get('reason', 'invalide')}")
        lines.append("   │")

    # Anomalies
    violations = details.get("violations") or []
    warnings = details.get("warnings") or []
    if violations or warnings:
        lines.append(f"   ┌─ ANOMALIES")
        for v in violations:
            lines.append(f"   │  ❌ {v}")
        for w in warnings:
            lines.append(f"   │  ⚠️  {w}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  PHASE 3 — OCR zones manuscrites
# ══════════════════════════════════════════════════════════════════
def format_phase3(p: Dict[str, Any]) -> str:
    details = p.get("details", {})
    lines = []
    lines.append(f"Phase 3 — OCR EXTRACTION   : {phase_icon(p)} "
                 f"({p.get('duration_ms', 0)} ms)")
    lines.append(f"   Score : {round(p.get('score', 0), 4)}")
    lines.append("")

    extracted = details.get("extracted", {}) or {}
    if extracted:
        lines.append("   ┌─ DONNÉES EXTRAITES DU CHÈQUE")
        champs = [
            ("banque",           "Banque              "),
            ("beneficiaire",     "Bénéficiaire        "),
            ("montant_chiffres", "Montant (chiffres)  "),
            ("montant_lettres",  "Montant (lettres)   "),
            ("date_lieu",        "Date et lieu        "),
            ("agence",           "Agence              "),
            ("cmc7",             "CMC7 (magnétique)   "),
        ]
        for cle, label in champs:
            v = extracted.get(cle)
            if v:
                s = str(v)
                if len(s) > 60:
                    s = s[:57] + "..."
                lines.append(f"   │  {label}: {s}")
            else:
                lines.append(f"   │  {label}: (non extrait)")
        lines.append("   │")

    lines.append(f"   ┌─ VALIDATION")
    cross = details.get("cross_validation_passed")
    lines.append(f"   │  Cross-validation chiffres↔lettres : {check(cross)}")
    review = details.get("human_review_required")
    lines.append(f"   │  Revue manuelle requise            : "
                 f"{'OUI' if review else 'NON'}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  PHASE 4 — Signature
# ══════════════════════════════════════════════════════════════════
def format_phase4(p: Dict[str, Any]) -> str:
    details = p.get("details", {})
    lines = []
    lines.append(f"Phase 4 — SIGNATURE        : {phase_icon(p)} "
                 f"({p.get('duration_ms', 0)} ms)")
    lines.append(f"   Décision : {details.get('decision', 'N/A')}")
    lines.append(f"   Score    : {round(p.get('score', 0), 4)}")
    lines.append(f"   Statut   : {details.get('verification_status', 'N/A')}")
    if details.get("note"):
        lines.append(f"   Note     : {details['note']}")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
#  RAPPORT COMPLET
# ══════════════════════════════════════════════════════════════════
def format_rapport(result: Dict[str, Any]) -> str:
    """Génère le rapport complet formaté (utilisé par main.py et les tests)."""
    lines = []
    lines.append("")
    lines.append("╔" + "═" * 60 + "╗")
    lines.append("║        RAPPORT DÉTAILLÉ — PIPELINE IA TUNICHEQUE         ║")
    lines.append("╚" + "═" * 60 + "╝")
    lines.append(f"ID chèque       : {result.get('cheque_id', 'N/A')}")
    d = result.get("final_decision", "")
    lines.append(f"Décision finale : {decision_icon(d)} {d}")
    lines.append(f"Temps total     : {result.get('total_time_ms', 0)} ms")
    lines.append("─" * 62)
    lines.append("")

    phases = result.get("phases", {})
    mapping_phases = [
        ("identification", format_phase1),
        ("compliance",     format_phase2),
        ("ocr",            format_phase3),
        ("signature",      format_phase4),
    ]
    for cle, fn in mapping_phases:
        p = phases.get(cle)
        if p:
            lines.append(fn(p))
            lines.append("")
            lines.append("─" * 62)
            lines.append("")

    # Synthèse finale
    lines.append("═" * 62)
    lines.append("   ACTION REQUISE :")
    du = str(d).upper()
    if du == "APPROVED":
        lines.append("   ✅ Chèque approuvé — traitement bancaire automatique")
    elif du.startswith("REJECTED"):
        lines.append(f"   ❌ Chèque rejeté — motif : {d}")
        lines.append("      Le chèque ne peut pas être traité.")
    else:
        lines.append(f"   ⚠️  Décision : {d}")
        lines.append("      → Transmettre à un agent pour vérification manuelle")
    lines.append("")
    return "\n".join(lines)