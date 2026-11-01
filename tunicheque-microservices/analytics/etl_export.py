"""
TuniCheque — ETL Export vers CSV pour Power BI Desktop
======================================================
Extrait les données des 3 bases PostgreSQL, transforme et exporte
en CSV enrichis importables directement dans Power BI Desktop.

Usage    : python etl_export.py
Prérequis: pip install psycopg2-binary pandas
Sortie   : ./exports/  (créé automatiquement)
"""

import os
import warnings
import pandas as pd
import psycopg2
from datetime import datetime, date

warnings.filterwarnings("ignore")

# ── Configuration connexions ──────────────────────────────────────────────────

DB_CHEQUES = dict(host="localhost", port=5432, dbname="database_cheques",
                  user="postgres", password="postgres")
DB_AUTH    = dict(host="localhost", port=5432, dbname="database_auth",
                  user="postgres", password="postgres")

EXPORT_DIR = os.path.join(os.path.dirname(__file__), "exports")
os.makedirs(EXPORT_DIR, exist_ok=True)

TS = datetime.now().strftime("%Y%m%d_%H%M")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _conn(cfg):
    return psycopg2.connect(**cfg)

def _export(conn, sql: str, name: str) -> pd.DataFrame:
    df = pd.read_sql_query(sql, conn)
    path = os.path.join(EXPORT_DIR, f"{name}_{TS}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  ✓  {name:<30} {len(df):>5} lignes  →  {os.path.basename(path)}")
    return df


# ── PHASE 1 : EXTRACT ─────────────────────────────────────────────────────────

def extract_cheques(conn) -> pd.DataFrame:
    return _export(conn, """
        SELECT
            c.id::text                                                  AS cheque_id,
            c.created_at                                                AS datetime_depot,
            c.created_at::date                                          AS date_depot,
            EXTRACT(YEAR  FROM c.created_at)::int                       AS annee,
            EXTRACT(MONTH FROM c.created_at)::int                       AS mois,
            EXTRACT(DOW   FROM c.created_at)::int                       AS jour_semaine,
            c.status                                                    AS statut,
            c.fraude_detectee::int                                      AS est_fraude,
            COALESCE(c.montant_extrait, 0)                              AS montant_tnd,
            COALESCE(c.ai_score_global, 0)                              AS score_ia,
            COALESCE(c.pipeline_ms, 0)                                  AS pipeline_ms,
            c.source                                                    AS canal,
            c.agent_id::text                                            AS agent_id,
            c.beneficiaire_id::text                                     AS beneficiaire_id,
            c.tireur_id::text                                           AS tireur_id,
            c.emetteur_nom
        FROM cheques c
        ORDER BY c.created_at DESC
    """, "extract_cheques")


def extract_ai_phases(conn) -> pd.DataFrame:
    return _export(conn, """
        SELECT
            ar.cheque_id::text,
            ar.phase,
            ROUND(ar.score::numeric, 4)  AS score,
            ar.passed::int               AS passe,
            ar.decision,
            ar.duration_ms
        FROM ai_results ar
        ORDER BY ar.created_at DESC
    """, "extract_ai_phases")


def extract_reclamations(conn) -> pd.DataFrame:
    return _export(conn, """
        SELECT
            r.id::text                AS reclamation_id,
            r.created_at::date        AS date,
            r.statut,
            r.numero_cheque,
            r.cheque_id::text,
            EXTRACT(EPOCH FROM (COALESCE(r.updated_at, NOW()) - r.created_at))
                / 3600.0              AS delai_h
        FROM reclamations r
        ORDER BY r.created_at DESC
    """, "extract_reclamations")


def extract_agents(conn) -> pd.DataFrame:
    return _export(conn, """
        SELECT
            u.id::text         AS agent_id,
            u.full_name        AS agent_nom,
            u.email,
            u.role,
            u.active::int      AS actif,
            u.created_at::date AS date_inscription
        FROM users u
        WHERE u.role IN ('AGENT', 'ADMIN')
    """, "extract_agents")


def extract_clients(conn) -> pd.DataFrame:
    return _export(conn, """
        SELECT
            ba.user_id::text           AS client_id,
            ba.rib,
            ba.nom_client,
            ba.bank_code,
            ba.created_at::date        AS date_inscription_rib
        FROM bank_accounts ba
    """, "extract_clients")


# ── PHASE 2 : TRANSFORM ───────────────────────────────────────────────────────

def transform(df_cheques: pd.DataFrame, df_agents: pd.DataFrame,
              df_phases: pd.DataFrame) -> pd.DataFrame:
    """
    Enrichissement croisé :
      - Join cheques ↔ agents (nom_agent)
      - Pivot phases IA (score par phase en colonnes)
      - Ajout features analytiques
    """
    # Join agent nom
    df = df_cheques.merge(
        df_agents[["agent_id", "agent_nom"]],
        on="agent_id", how="left"
    )

    # Pivot phases IA : PHASE_1..4 en colonnes
    if not df_phases.empty:
        pivot = (
            df_phases.pivot_table(
                index="cheque_id", columns="phase",
                values="score", aggfunc="first"
            )
            .rename(columns={
                "PHASE_1": "score_p1_identification",
                "PHASE_2": "score_p2_ocr",
                "PHASE_3": "score_p3_signature",
                "PHASE_4": "score_p4_kyc",
            })
            .reset_index()
        )
        df = df.merge(pivot, on="cheque_id", how="left")

    # Features analytiques
    df["est_valide"]      = (df["statut"] == "VALIDE").astype(int)
    df["est_rejete"]      = df["statut"].isin(["REJETE","FRAUDE_DETECTEE"]).astype(int)
    df["est_en_cours"]    = df["statut"].isin(["EN_ATTENTE","EN_TRAITEMENT"]).astype(int)
    df["duree_sec"]       = (df["pipeline_ms"] / 1000).round(2)
    df["niveau_confiance"] = pd.cut(
        df["score_ia"],
        bins=[0, 0.75, 0.90, 1.0],
        labels=["Faible confiance", "Confiance moyenne", "Haute confiance"],
        include_lowest=True
    )
    df["est_weekend"] = df["jour_semaine"].isin([0, 6]).astype(int)  # 0=dim, 6=sam

    return df


# ── PHASE 3 : DIM DATES ──────────────────────────────────────────────────────

def build_dim_dates() -> pd.DataFrame:
    dates = pd.date_range(start="2024-01-01", end=datetime.today(), freq="D")
    mois_fr = {1:"Janvier",2:"Février",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
               7:"Juillet",8:"Août",9:"Septembre",10:"Octobre",11:"Novembre",12:"Décembre"}
    jours_fr = {0:"Lundi",1:"Mardi",2:"Mercredi",3:"Jeudi",4:"Vendredi",5:"Samedi",6:"Dimanche"}
    df = pd.DataFrame({
        "date":            dates.date,
        "annee":           dates.year,
        "trimestre":       dates.quarter,
        "mois_num":        dates.month,
        "mois_label":      dates.month.map(mois_fr),
        "semaine_iso":     dates.isocalendar().week.values,
        "jour":            dates.day,
        "jour_semaine_num": dates.dayofweek,
        "jour_semaine_label": dates.dayofweek.map(jours_fr),
        "est_weekend":     (dates.dayofweek >= 5).astype(int),
        "est_fin_de_mois": dates.is_month_end.astype(int),
        "est_debut_mois":  dates.is_month_start.astype(int),
    })
    path = os.path.join(EXPORT_DIR, f"dim_dates_{TS}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  ✓  {'dim_dates':<30} {len(df):>5} lignes  →  {os.path.basename(path)}")
    return df


# ── MAIN ─────────────────────────────────────────────────────────────────────

def run():
    sep = "=" * 62
    print(sep)
    print("  TuniCheque ETL — Export Power BI Desktop")
    print(f"  Démarrage : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(sep)

    # ── 1. Extract ──────────────────────────────────────────────────
    print("\n[1/4] EXTRACT — database_cheques")
    with _conn(DB_CHEQUES) as conn:
        df_cheques = extract_cheques(conn)
        df_phases  = extract_ai_phases(conn)
        extract_reclamations(conn)

    print("\n[2/4] EXTRACT — database_auth")
    with _conn(DB_AUTH) as conn:
        df_agents  = extract_agents(conn)
        extract_clients(conn)

    # ── 2. Transform ─────────────────────────────────────────────────
    print("\n[3/4] TRANSFORM — enrichissement croisé")
    df_rapport = transform(df_cheques, df_agents, df_phases)
    path = os.path.join(EXPORT_DIR, f"rapport_principal_{TS}.csv")
    df_rapport.to_csv(path, index=False, encoding="utf-8-sig")
    print(f"  ✓  {'rapport_principal':<30} {len(df_rapport):>5} lignes  →  {os.path.basename(path)}")

    # ── 3. Dimension dates ────────────────────────────────────────────
    print("\n[4/4] LOAD — dimensions")
    build_dim_dates()

    # ── Résumé ────────────────────────────────────────────────────────
    print(f"\n{sep}")
    print(f"  ETL terminé : {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(f"  Fichiers    : {EXPORT_DIR}")
    print(sep)
    print("""
  Prochaines étapes Power BI Desktop :
  ─────────────────────────────────────────────────────────────
  1. Ouvrir Power BI Desktop (gratuit : https://powerbi.com)
  2. Accueil > Obtenir les données > Texte/CSV
  3. Importer (dans cet ordre) :
       • rapport_principal_*.csv   — table de fait principale
       • dim_dates_*.csv           — dimension temporelle
       • extract_reclamations_*.csv
       • extract_agents_*.csv
  4. Modèle > Créer les relations :
       rapport_principal.date_depot  ↔  dim_dates.date
       rapport_principal.agent_id    ↔  extract_agents.agent_id
  5. Créer les visuels (voir guide dans l'interface admin)
  6. Fichier > Publier sur Power BI Service
  7. Rapport > Fichier > Incorporer > Publier sur le web
  8. Copier l'URL iframe → coller dans l'interface admin TuniCheque
  ─────────────────────────────────────────────────────────────
""")


if __name__ == "__main__":
    run()
