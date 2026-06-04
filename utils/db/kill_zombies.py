"""Kill zombie dbt processes holding locks on the warehouse.

When a `dbt run` is killed (Ctrl-C, timeout, or process death), the
PostgreSQL backend it spawned may survive and continue holding an
`AccessShareLock` on the model's parent tables. Subsequent dbt runs
that need an `AccessExclusiveLock` for `CREATE TABLE AS SELECT` then
hang indefinitely, blocked by the zombie. The dbt run log typically
ends at "Opening a new connection, currently in state init" with
no progress, while `pg_stat_activity` shows the old sessions still
in `state=active`, often waiting on `Lock/transactionid`.

This script terminates all non-idle backends on the current database
*other than* the one running this script. Use it when a dbt run hangs
for several minutes with no progress and `utils.db.check_dbt_state`
shows zombie processes.

Run from project root:

    python -m utils.db.kill_zombies

The script does not filter by application name; it kills every active
session. Do not run it on a database shared with other tooling.
"""

import os
import psycopg2
from dotenv import load_dotenv, find_dotenv

load_dotenv(dotenv_path=find_dotenv())


def main():
    conn = psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=os.environ["DB_PORT"],
        dbname=os.environ["DB_NAME"],
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
    )
    cur = conn.cursor()
    cur.execute("""
        select pid, state, query_start, left(query, 60)
        from pg_stat_activity
        where datname = current_database()
          and pid != pg_backend_pid()
          and state != 'idle'
    """)
    rows = cur.fetchall()
    print(f"Killing {len(rows)} zombie processes:")
    for pid, state, started, q in rows:
        print(f"  pid={pid} state={state} started={started}")
        cur.execute("select pg_terminate_backend(%s)", (pid,))
        print(f"    -> result: {cur.fetchone()[0]}")
    conn.close()
    print("Done")


if __name__ == "__main__":
    main()
