import os
import sys
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

try:
    import structlog
    logger = structlog.get_logger()
except ImportError:
    import logging
    logger = logging.getLogger(__name__)

load_dotenv()


def create_db_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://cheque_admin:kmss-a5kK@localhost:5432/cheque_db"
    )
    engine = create_engine(
        db_url,
        pool_size     = 5,
        max_overflow  = 10,
        pool_recycle  = 1800,
        pool_pre_ping = True,
    )
    return engine


db_engine = create_db_engine()


def get_config(cle: str, defaut=None):
    try:
        with db_engine.connect() as conn:
            row = conn.execute(
                text("SELECT valeur, type_valeur FROM configurations WHERE cle = :k"),
                {"k": cle}
            ).fetchone()
            if row is None:
                return defaut
            valeur, type_valeur = row
            if type_valeur == "FLOAT":   return float(valeur)
            if type_valeur == "INTEGER": return int(valeur)
            if type_valeur == "BOOLEAN": return valeur.lower() == "true"
            return valeur
    except Exception as e:
        logger.error("config_read_error", key=cle, error=str(e))
        return defaut


def test_connexion() -> bool:
    try:
        with db_engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM cheques")).fetchone()
            logger.info("db_connexion_ok", nb_cheques=result[0])
            return True
    except Exception as e:
        logger.warning("db_connexion_failed", error=str(e))
        return False

