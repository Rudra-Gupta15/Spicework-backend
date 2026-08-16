from backend import legacy_db


def get_audit_indexes():
    return legacy_db.get_audit_enrichment_indexes()
