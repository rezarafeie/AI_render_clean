"""Durable execution leases, atomic transitions and cost reservations on one VPS.

Keep on persistent local disk, not NFS. This ledger does not replace Studio jobs.
Signed URLs, API keys and manifest user content are deliberately not stored here.
"""
from __future__ import annotations

import json
import math
import secrets
import hashlib
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

FINAL = {'completed', 'failed', 'cancelled'}
NEXT = {
    'queued': {'provisioning', 'cancelled', 'failed'},
    'provisioning': {'preparing', 'failed', 'cancelled'},
    'preparing': {'downloading', 'failed', 'cancelled'},
    'downloading': {'rendering', 'failed', 'cancelled'},
    'rendering': {'uploading', 'failed', 'cancelled'},
    'uploading': {'completed', 'failed', 'cancelled'},
}


class Conflict(ValueError):
    pass


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS cloud_render_executions (
                id TEXT PRIMARY KEY, user_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
                state TEXT NOT NULL, backend TEXT NOT NULL, pod_id TEXT,
                created REAL NOT NULL, updated REAL NOT NULL, deadline REAL NOT NULL,
                lease_owner TEXT, lease_until REAL, cancel_requested INTEGER NOT NULL DEFAULT 0,
                reservation REAL NOT NULL, details TEXT NOT NULL DEFAULT '{}',
                cleanup_pending INTEGER NOT NULL DEFAULT 0)''')
            # Additive migration for locally persisted foundation ledgers.
            columns = {r['name'] for r in db.execute('PRAGMA table_info(cloud_render_executions)')}
            for name, declaration in {
                'pod_name': 'TEXT', 'image': 'TEXT', 'create_attempted': 'INTEGER NOT NULL DEFAULT 0',
                'worker_token_hash': 'TEXT', 'event_sequence': 'INTEGER NOT NULL DEFAULT 0',
                'heartbeat': 'REAL', 'progress': 'REAL', 'finished': 'REAL',
            }.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE cloud_render_executions ADD COLUMN {name} {declaration}')
            db.execute('''CREATE TABLE IF NOT EXISTS cloud_render_costs (
                job_id TEXT NOT NULL, source TEXT NOT NULL, reference TEXT NOT NULL,
                category TEXT NOT NULL, usd REAL NOT NULL, measured INTEGER NOT NULL,
                updated REAL NOT NULL, PRIMARY KEY(job_id,source,reference,category))''')
            db.execute('CREATE TABLE IF NOT EXISTS cloud_render_policy (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS cloud_render_dcs (dc TEXT PRIMARY KEY, bad_until REAL NOT NULL DEFAULT 0, last_ok REAL NOT NULL DEFAULT 0, fails INTEGER NOT NULL DEFAULT 0)')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def reserve(self, job_id, user, fingerprint, backend, *, estimate, max_cost,
                daily_budget, monthly_budget, max_workers, max_gpu, timeout):
        if (any(not math.isfinite(v) or v <= 0 for v in (estimate, max_cost, daily_budget, monthly_budget))
                or estimate > max_cost or max_workers < 1 or timeout <= 0 or timeout > 21600):
            raise Conflict('Invalid reservation')
        if backend not in {'runpod_cpu', 'runpod_gpu'}:
            raise Conflict('Invalid backend')
        now = time.time()
        utc = time.gmtime(now)
        import calendar
        day = calendar.timegm((*utc[:3], 0, 0, 0))
        month = calendar.timegm((utc.tm_year, utc.tm_mon, 1, 0, 0, 0))
        with self.transaction() as db:
            old = db.execute('SELECT * FROM cloud_render_executions WHERE id=?', (job_id,)).fetchone()
            if old:
                if old['user_id'] != user or old['fingerprint'] != fingerprint or old['backend'] != backend:
                    raise Conflict('Idempotency key reused with different input')
                return dict(old)
            # Cleanup-pending Pods still count against concurrency even after terminal failure.
            active = db.execute("SELECT backend FROM cloud_render_executions WHERE state NOT IN ('completed','failed','cancelled') OR cleanup_pending=1").fetchall()
            if len(active) >= max_workers or (backend == 'runpod_gpu' and sum(r['backend'] == backend for r in active) >= max_gpu):
                raise Conflict('Concurrency limit')
            for since, budget in ((day, daily_budget), (month, monthly_budget)):
                spent = db.execute("""SELECT COALESCE(SUM(MAX(reservation,
                    COALESCE((SELECT SUM(usd) FROM cloud_render_costs c WHERE c.job_id=e.id AND c.measured=1),0))),0)
                    FROM cloud_render_executions e WHERE created>=? OR
                    state NOT IN ('completed','failed','cancelled') OR cleanup_pending=1""", (since,)).fetchone()[0]
                if spent + estimate > budget:
                    raise Conflict('Budget limit')
            db.execute('INSERT INTO cloud_render_executions (id,user_id,fingerprint,state,backend,created,updated,deadline,reservation) VALUES (?,?,?,?,?,?,?,?,?)',
                       (job_id, user, fingerprint, 'queued', backend, now, now, now + timeout, estimate))
            return dict(db.execute('SELECT * FROM cloud_render_executions WHERE id=?', (job_id,)).fetchone())

    def claim(self, job_id, user, owner, seconds=90):
        now = time.time()
        with self.transaction() as db:
            changed = db.execute("UPDATE cloud_render_executions SET lease_owner=?,lease_until=?,updated=? WHERE id=? AND user_id=? AND state NOT IN ('completed','failed','cancelled') AND deadline>? AND (lease_until IS NULL OR lease_until<? OR lease_owner=?)",
                                 (owner, now + seconds, now, job_id, user, now, now, owner)).rowcount
            if not changed:
                raise Conflict('Execution unavailable or already leased')

    def transition(self, job_id, user, owner, expected, state, details=None):
        if state not in NEXT.get(expected, set()):
            raise Conflict('Invalid transition')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            if not row or row['state'] != expected or row['lease_owner'] != owner or (row['lease_until'] or 0) < time.time():
                raise Conflict('Stale execution')
            if row['cancel_requested'] and state not in {'failed', 'cancelled'}:
                raise Conflict('Cancellation requested')
            db.execute('UPDATE cloud_render_executions SET state=?,updated=?,details=? WHERE id=?',
                       (state, time.time(), json.dumps({**json.loads(row['details']), **(details or {})}), job_id))

    def cancel(self, job_id, user):
        with self.transaction() as db:
            return bool(db.execute("UPDATE cloud_render_executions SET cancel_requested=1,updated=? WHERE id=? AND user_id=? AND state NOT IN ('completed','failed','cancelled')", (time.time(), job_id, user)).rowcount)

    def bind_pod(self, job_id, user, owner, pod_id):
        with self.transaction() as db:
            # A fast worker may report preparing/failure before create() returns.
            # Still bind that exact attempt for cleanup; never resurrect its state.
            if not db.execute("UPDATE cloud_render_executions SET pod_id=?,cleanup_pending=1 WHERE id=? AND user_id=? AND (state='provisioning' OR create_attempted=1) AND lease_owner=? AND lease_until>? AND pod_id IS NULL",
                              (pod_id, job_id, user, owner, time.time())).rowcount:
                raise Conflict('Pod binding rejected')

    def cleanup_done(self, job_id, pod_id):
        with self.transaction() as db:
            db.execute('UPDATE cloud_render_executions SET cleanup_pending=0 WHERE id=? AND pod_id=?', (job_id, pod_id))

    def rejected_create(self, job_id, user):
        """Only for definite pre-create validation/auth rejection, never a timeout."""
        with self.transaction() as db:
            db.execute("UPDATE cloud_render_executions SET cleanup_pending=0 WHERE id=? AND user_id=? AND pod_id IS NULL AND state='failed'",
                       (job_id,user))

    def resources_to_reap(self):
        with self.transaction() as db:
            return [dict(r) for r in db.execute("SELECT * FROM cloud_render_executions WHERE cleanup_pending=1 AND (state IN ('completed','failed','cancelled') OR cancel_requested=1 OR deadline<?)", (time.time(),))]

    def get(self, job_id, user):
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            if not row:
                raise Conflict('Execution not found')
            return dict(row)

    def begin_create(self, job_id, user, owner, pod_name, image, token):
        """Persist the intent BEFORE the network call; one POST in this execution's life.

        A crash after this commit is deliberately ambiguous. Recovery lists/deletes
        the exact nonce-bearing name, never creates another billable Pod.
        """
        with self.transaction() as db:
            if not db.execute("""UPDATE cloud_render_executions SET state='provisioning',
                    pod_name=?,image=?,create_attempted=1,cleanup_pending=1,
                    worker_token_hash=?,updated=?
                    WHERE id=? AND user_id=? AND state='queued' AND create_attempted=0
                    AND lease_owner=? AND lease_until>? AND deadline>? AND cancel_requested=0""",
                    (pod_name, image, hashlib.sha256(token.encode()).hexdigest(), time.time(),
                     job_id, user, owner, time.time(), time.time())).rowcount:
                raise Conflict('Create already attempted or execution unavailable')

    def finish(self, job_id, user, state, error_code=None):
        """VPS control-plane terminal decision, never a worker success assertion."""
        if state not in {'failed', 'cancelled'}:
            raise Conflict('Invalid terminal decision')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            details = {**(json.loads(row['details']) if row else {}), 'error_code': error_code}
            db.execute("""UPDATE cloud_render_executions SET state=?,updated=?,finished=?,details=?
                WHERE id=? AND user_id=? AND state NOT IN ('completed','failed','cancelled')""",
                (state, time.time(), time.time(), json.dumps(details), job_id, user))

    def recent_failures(self, error_code, within_seconds: float) -> int:
        """How many executions ended `failed` with this control-plane error code (or any of several) in the last `within_seconds` (a circuit breaker reads it; never raises)."""
        codes = {error_code} if isinstance(error_code, str) else set(error_code)
        try:
            with self.transaction() as db:
                rows = db.execute("SELECT details FROM cloud_render_executions WHERE state='failed' AND finished>?", (time.time() - within_seconds,)).fetchall()
            return sum(1 for r in rows if json.loads(r['details'] or '{}').get('error_code') in codes)
        except Exception:
            return 0

    def dc_mark_bad(self, dc: str, cooldown_seconds: float) -> None:
        """A Pod placed in this data center never reported: keep new Pods out of it for a while (never raises)."""
        try:
            with self.transaction() as db:
                db.execute('INSERT INTO cloud_render_dcs(dc,bad_until,fails) VALUES(?,?,1) ON CONFLICT(dc) DO UPDATE SET bad_until=excluded.bad_until, fails=fails+1',
                           (dc, time.time() + cooldown_seconds))
        except Exception:
            pass

    def dc_mark_ok(self, dc: str) -> None:
        """A Pod placed in this data center started and rendered: it is preferred again and its cooldown ends (never raises)."""
        try:
            with self.transaction() as db:
                db.execute('INSERT INTO cloud_render_dcs(dc,last_ok) VALUES(?,?) ON CONFLICT(dc) DO UPDATE SET last_ok=excluded.last_ok, bad_until=0, fails=0',
                           (dc, time.time()))
        except Exception:
            pass

    def dc_order(self, candidates: list[str]) -> list[str]:
        """The candidate data centers best first: ones that worked most recently, then unknown ones in the configured order; ones in cooldown are left out
        unless every candidate is in cooldown (then the one whose cooldown ends first comes first). Never raises."""
        now = time.time()
        try:
            with self.transaction() as db:
                rows = {r['dc']: (r['bad_until'], r['last_ok']) for r in db.execute('SELECT dc,bad_until,last_ok FROM cloud_render_dcs').fetchall()}
        except Exception:
            rows = {}
        good = [(dc, i) for i, dc in enumerate(candidates) if rows.get(dc, (0, 0))[0] <= now]
        if good:
            return [dc for dc, i in sorted(good, key=lambda x: (-rows.get(x[0], (0, 0))[1], x[1]))]
        return sorted(candidates, key=lambda dc: rows.get(dc, (0, 0))[0])

    def record_event(self, job_id, user, token, sequence, observation):
        """Authenticate scoped, expiring worker observations with replay protection."""
        from .contracts import Observation
        event = Observation.model_validate(observation)
        if event.state in {'queued', 'provisioning', 'completed'}:
            raise Conflict('Worker cannot authorize this state')
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise Conflict('Invalid event sequence')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            now = time.time()
            if (not row or not row['worker_token_hash'] or row['deadline'] <= now
                    or not secrets.compare_digest(row['worker_token_hash'], hashlib.sha256(token.encode()).hexdigest())):
                raise Conflict('Worker credential invalid or expired')
            if sequence <= row['event_sequence']:
                return False
            if row['cancel_requested'] or row['state'] in FINAL:
                raise Conflict('Execution is no longer active')
            if sequence != row['event_sequence'] + 1:
                raise Conflict('Event sequence gap')
            if event.state != row['state'] and event.state not in NEXT.get(row['state'], set()):
                raise Conflict('Invalid worker transition')
            progress = event.progress
            if event.state == row['state'] and progress is not None and row['progress'] is not None:
                progress = max(progress, row['progress'])
            db.execute('''UPDATE cloud_render_executions SET state=?,event_sequence=?,heartbeat=?,
                       updated=?,progress=?,details=?,finished=? WHERE id=?''',
                       (event.state, sequence, now, now, progress,
                        json.dumps({**json.loads(row['details']), 'error_code': event.error_code}), now if event.state in FINAL else None, job_id))
            return True

    def complete(self, job_id, user, *, expected_pod_id, output_receipt):
        """Called only AFTER independent output hash/media validation on the VPS."""
        if (not isinstance(output_receipt, dict) or not output_receipt.get('sha256')
                or not output_receipt.get('object_key')):
            raise Conflict('Verified receipt required')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            if row and row['state'] == 'completed':
                previous = json.loads(row['details']).get('output', {})
                if row['pod_id'] == expected_pod_id and all(previous.get(k) == output_receipt.get(k) for k in ('sha256','object_key','size')):
                    return
                raise Conflict('Different output was already published')
            if not db.execute("""UPDATE cloud_render_executions SET state='completed',finished=?,updated=?,
                    details=? WHERE id=? AND user_id=? AND state='uploading' AND pod_id=?
                    AND cancel_requested=0 AND deadline>?""",
                    (time.time(), time.time(), json.dumps({**(json.loads(row['details']) if row else {}), 'output': output_receipt}), job_id, user,
                     expected_pod_id, time.time())).rowcount:
                raise Conflict('Output publication is no longer authorized')

    def reconciliation_rows(self, *, idle_seconds=180):
        now = time.time()
        with self.transaction() as db:
            return [dict(row) for row in db.execute("""SELECT * FROM cloud_render_executions
                WHERE state NOT IN ('completed','failed','cancelled') OR cleanup_pending=1""")]

    def attach_discovered(self, job_id, pod_id):
        # For cleanup only; cannot turn an ambiguous/failed execution back on.
        with self.transaction() as db:
            if not db.execute('''UPDATE cloud_render_executions SET pod_id=?
                    WHERE id=? AND cleanup_pending=1 AND pod_id IS NULL AND create_attempted=1''',
                    (pod_id, job_id)).rowcount:
                raise Conflict('Discovered Pod binding rejected')

    def snapshot(self, job_id, user, token, sequence, history, observation, *, timings=None, resources=None):
        """Apply an authenticated mailbox snapshot, including missed stage transitions.

        Object stores can overwrite an intermediate progress sample before a VPS
        poll. A small ordered stage history lets us validate the path without
        requiring a database write for every encoded frame.
        """
        from .contracts import Observation
        event = Observation.model_validate(observation)
        order = ['preparing', 'downloading', 'rendering', 'uploading']
        if (type(sequence) is not int or sequence < 1 or sequence > 100000
                or history != order[:len(history)] or not 1 <= len(history) <= 4
                or event.state not in {history[-1], 'failed', 'cancelled'}):
            raise Conflict('Invalid worker snapshot')
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id, user)).fetchone()
            now = time.time()
            if (not row or not row['worker_token_hash'] or row['deadline'] <= now
                    or not secrets.compare_digest(row['worker_token_hash'], hashlib.sha256(token.encode()).hexdigest())):
                raise Conflict('Invalid worker credential')
            if sequence <= row['event_sequence']:
                return False
            if row['cancel_requested'] or row['state'] in FINAL:
                raise Conflict('Execution no longer active')
            if row['state'] not in {'provisioning', *history}:
                raise Conflict('Stage history does not extend execution')
            progress = event.progress
            if event.state == row['state'] and progress is not None and row['progress'] is not None:
                progress = max(progress, row['progress'])
            db.execute('''UPDATE cloud_render_executions SET state=?,event_sequence=?,heartbeat=?,updated=?,
                progress=?,details=?,finished=? WHERE id=?''',
                (event.state, sequence, now, now, progress, json.dumps({**json.loads(row['details']), 'error_code': event.error_code,
                                                                     **({'timings':timings} if timings is not None else {}),
                                                                     **({'resources':resources} if resources else {})}),
                 now if event.state in FINAL else None, job_id))
            return True

    def plan_storage(self, job_id, user, mailbox_key, control_key, output_key, *, spec=None, local_output=None):
        """Persist references only, never URLs. Needed for recovery after API restart."""
        with self.transaction() as db:
            row = db.execute('SELECT details FROM cloud_render_executions WHERE id=? AND user_id=? AND state=\'queued\'', (job_id, user)).fetchone()
            if not row:
                raise Conflict('Storage plan unavailable')
            details = json.loads(row['details'])
            details['storage'] = {'mailbox_key': mailbox_key, 'control_key': control_key, 'output_key': output_key}
            if spec is not None:
                details['render_spec'] = spec
            if local_output is not None:
                details['local_output'] = local_output
            db.execute('UPDATE cloud_render_executions SET details=? WHERE id=?', (json.dumps(details), job_id))

    def record_cost(self, job_id, source, reference, category, usd, *, measured):
        if not math.isfinite(usd) or usd < 0 or category not in {'provider_pod_total','compute','startup','idle','storage','network','failed_attempt'}:
            raise ValueError('Invalid cost observation')
        with self.transaction() as db:
            if not db.execute('SELECT 1 FROM cloud_render_executions WHERE id=?', (job_id,)).fetchone():
                raise Conflict('Cost execution not found')
            # Billing bucket totals may grow during the day. Replace a bucket,
            # never add the same bill on every reconciliation tick.
            db.execute('''INSERT INTO cloud_render_costs VALUES (?,?,?,?,?,?,?)
                ON CONFLICT(job_id,source,reference,category) DO UPDATE SET
                usd=excluded.usd,measured=excluded.measured,updated=excluded.updated''',
                (job_id,source,reference,category,usd,int(measured),time.time()))

    def compute_finished(self, job_id, user, receipt):
        """Candidate exists in storage. Free compute before slow VPS delivery/QC."""
        with self.transaction() as db:
            row = db.execute("SELECT details FROM cloud_render_executions WHERE id=? AND user_id=? AND state='uploading' AND cancel_requested=0", (job_id,user)).fetchone()
            if not row:
                raise Conflict('Execution cannot finish compute')
            details = json.loads(row['details'])
            details.update(compute_finished=True, candidate=receipt)
            db.execute('UPDATE cloud_render_executions SET details=? WHERE id=?', (json.dumps(details),job_id))

    def resume_delivery(self, job_id, user, seconds):
        """Explicit retry of already-finished compute, never a new provider request."""
        with self.transaction() as db:
            row = db.execute('SELECT * FROM cloud_render_executions WHERE id=? AND user_id=?', (job_id,user)).fetchone()
            if not row or row['state'] != 'failed' or row['cancel_requested'] or row['cleanup_pending'] or not json.loads(row['details']).get('compute_finished'):
                return False
            db.execute("UPDATE cloud_render_executions SET state='uploading',deadline=?,updated=?,finished=NULL WHERE id=?",
                       (time.time()+seconds,time.time(),job_id))
            return True

    def summaries(self, limit=100):
        with self.transaction() as db:
            rows = db.execute('''SELECT id,user_id,state,backend,pod_id,created,finished,progress,
                    cancel_requested,cleanup_pending,reservation,
                    (SELECT SUM(usd) FROM cloud_render_costs c WHERE c.job_id=e.id AND c.measured=1) provider_charge_usd
                    FROM cloud_render_executions e ORDER BY created DESC LIMIT ?''', (min(500,max(1,limit)),))
            return [dict(row) for row in rows]

    def owned_pods(self):
        with self.transaction() as db:
            return {row['pod_id']:row['id'] for row in db.execute('SELECT id,pod_id FROM cloud_render_executions WHERE pod_id IS NOT NULL')}

    def policy(self):
        with self.transaction() as db:
            row = db.execute('SELECT value FROM cloud_render_policy WHERE id=1').fetchone()
            return json.loads(row['value']) if row else {}

    def update_policy(self, values):
        with self.transaction() as db:
            row = db.execute('SELECT value FROM cloud_render_policy WHERE id=1').fetchone()
            merged = {**(json.loads(row['value']) if row else {}), **values}
            db.execute('INSERT INTO cloud_render_policy VALUES (1,?) ON CONFLICT(id) DO UPDATE SET value=excluded.value', (json.dumps(merged),))
