"""PostgreSQL state diagnostic for the dbt pipeline.

Prints row counts of dbt-managed tables, source freshness, active
queries (other than this one), and any locks held on `int.*` tables.
Use this when a `dbt run` hangs or behaves unexpectedly to find out
whether zombie dbt processes are holding locks on parent tables.

Run from project root:

    python -m utils.db.check_dbt_state

Exits 0 on success (the print is the output). Designed for ad-hoc
diagnostics, not CI.
"""

import os
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(dotenv_path=find_dotenv())


def _connect():
    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )


def main():
    conn = _connect()
    cur = conn.cursor()

    print("=== Table row counts (parents of int_eta_to_end_of_route) ===")
    for schema, table in [
        ("staging", "stg_previsao_raw"),
        ("staging", "stg_weather_raw"),
        ("int", "int_previsao_calculated"),
        ("int", "int_line_stops"),
    ]:
        try:
            cur.execute(f"select count(*) from {schema}.{table}")
            n = cur.fetchone()[0]
            print(f"  {schema}.{table:<28} {n:>12,}")
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            print(f"  {schema}.{table:<28}     (missing)")

    print("\n=== Last ingestion (staging source freshness) ===")
    cur.execute("select max(loaded_at) from staging.stg_previsao_raw")
    print(f"  stg_previsao_raw.max(loaded_at) = {cur.fetchone()[0]}")

    print("\n=== Active queries / locks ===")
    cur.execute("""
        select pid, state, query_start, wait_event_type, wait_event,
               left(query, 80) as query
        from pg_stat_activity
        where datname = current_database()
          and state != 'idle'
          and pid != pg_backend_pid()
        order by query_start
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (no active queries from other sessions)")
    else:
        for r in rows:
            print(f"  pid={r[0]} state={r[1]:<10} started={r[2]} wait={r[3]}/{r[4]}")
            print(f"    {r[5]}")

    print("\n=== Locks held on int.* tables ===")
    cur.execute("""
        select relation::regclass, mode, granted, count(*)
        from pg_locks l
        join pg_class c on c.oid = l.relation
        where c.relnamespace = 'int'::regnamespace
        group by relation, mode, granted
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (no locks on int.* tables)")
    else:
        for r in rows:
            print(f"  {r[0]}  mode={r[1]:<15} granted={r[2]}  count={r[3]}")

    conn.close()


if __name__ == "__main__":
    main()
