"""SQL for the database-level protections (PostgreSQL only).

Even a client connected directly to the database with the application's credentials cannot
alter an append-only record or delete a registry record: the triggers refuse it, and the runtime
role has no DELETE/TRUNCATE privilege in the first place (CDC ENF-3.6, EF-3 acceptance criteria).
"""

REFUSE_FUNCTION = """
CREATE OR REPLACE FUNCTION fluxaa_refuse() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'FLUXAA registry: % on % is forbidden', TG_OP, TG_TABLE_NAME
    USING ERRCODE = '42501',
          HINT = 'Registry records are never altered or deleted; record a rectification instead.';
END
$$;
"""


def append_only_sql(table: str) -> list[str]:
    return [
        f'DROP TRIGGER IF EXISTS fluxaa_append_only ON "{table}";',
        f'CREATE TRIGGER fluxaa_append_only BEFORE UPDATE OR DELETE ON "{table}" '
        f"FOR EACH ROW EXECUTE FUNCTION fluxaa_refuse();",
        f'DROP TRIGGER IF EXISTS fluxaa_no_truncate ON "{table}";',
        f'CREATE TRIGGER fluxaa_no_truncate BEFORE TRUNCATE ON "{table}" '
        f"FOR EACH STATEMENT EXECUTE FUNCTION fluxaa_refuse();",
    ]


def no_delete_sql(table: str) -> list[str]:
    return [
        f'DROP TRIGGER IF EXISTS fluxaa_no_delete ON "{table}";',
        f'CREATE TRIGGER fluxaa_no_delete BEFORE DELETE ON "{table}" '
        f"FOR EACH ROW EXECUTE FUNCTION fluxaa_refuse();",
        f'DROP TRIGGER IF EXISTS fluxaa_no_truncate ON "{table}";',
        f'CREATE TRIGGER fluxaa_no_truncate BEFORE TRUNCATE ON "{table}" '
        f"FOR EACH STATEMENT EXECUTE FUNCTION fluxaa_refuse();",
    ]


def drop_sql(table: str) -> list[str]:
    return [
        f'DROP TRIGGER IF EXISTS fluxaa_append_only ON "{table}";',
        f'DROP TRIGGER IF EXISTS fluxaa_no_delete ON "{table}";',
        f'DROP TRIGGER IF EXISTS fluxaa_no_truncate ON "{table}";',
    ]
