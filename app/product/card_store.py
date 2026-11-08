"""Owned, explicitly saved experience cards. Conversation history stays ephemeral."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.agent.errors import RuntimeFailure


class CardStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @contextmanager
    def db(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=5)) as db, db:
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA secure_delete=ON')
            db.execute('CREATE TABLE IF NOT EXISTS cards (owner TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(owner,id))')
            db.execute('CREATE TABLE IF NOT EXISTS receipts (owner TEXT NOT NULL, operation TEXT NOT NULL, fingerprint TEXT NOT NULL, card_id TEXT NOT NULL, PRIMARY KEY(owner,operation))')
            db.execute('CREATE TABLE IF NOT EXISTS memory_clock (owner TEXT PRIMARY KEY, revision INTEGER NOT NULL)')
            yield db

    @staticmethod
    def _tick(db, owner):
        db.execute('INSERT INTO memory_clock VALUES (?,1) ON CONFLICT(owner) DO UPDATE SET revision=revision+1', (owner,))

    def list(self, owner):
        with self.db() as db:
            return [json.loads(r['payload']) for r in db.execute('SELECT payload FROM cards WHERE owner=? ORDER BY rowid DESC LIMIT 500', (owner,))]

    def recall(self, owner):
        with self.db() as db:
            db.execute('BEGIN')
            row = db.execute('SELECT revision FROM memory_clock WHERE owner=?', (owner,)).fetchone()
            cards = [json.loads(r['payload']) for r in db.execute('SELECT payload FROM cards WHERE owner=? ORDER BY rowid DESC LIMIT 500', (owner,))]
            return (row[0] if row else 0), [c for c in cards if c['remember_for_future']][:3]

    def replay(self, owner, operation, request):
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        with self.db() as db:
            receipt = db.execute('SELECT * FROM receipts WHERE owner=? AND operation=?', (owner, operation)).fetchone()
            if not receipt:
                return None
            if receipt['fingerprint'] != fingerprint:
                raise RuntimeFailure('operation_id_conflict', '操作编号已经用于其他内容。')
            row = db.execute('SELECT payload FROM cards WHERE owner=? AND id=?', (owner, receipt['card_id'])).fetchone()
            if not row:
                raise RuntimeFailure('card_deleted', '经历卡已删除，旧请求不会重新创建。')
            return json.loads(row['payload'])

    def save(self, owner, operation, request, *, fields):
        replay = self.replay(owner, operation, request)
        if replay is not None:
            return replay
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        card = {**request, 'card_id': str(uuid4()), 'revision': 1,
                'created_at': datetime.now(timezone.utc).isoformat(), 'fields': fields,
                'understanding_revision': request['expected_revision']}
        card.pop('operation_id', None)
        card.pop('expected_revision', None)
        # Letting go does not quietly retain the discarded text in memory or a card.
        card['release_text'] = ''
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            receipt = db.execute('SELECT * FROM receipts WHERE owner=? AND operation=?', (owner, operation)).fetchone()
            if receipt:
                if receipt['fingerprint'] != fingerprint:
                    raise RuntimeFailure('operation_id_conflict', '操作编号已经用于其他内容。')
                row = db.execute('SELECT payload FROM cards WHERE owner=? AND id=?', (owner, receipt['card_id'])).fetchone()
                if row is None:
                    raise RuntimeFailure('card_deleted', '经历卡已删除，旧请求不会重新创建。')
                return json.loads(row['payload'])
            if db.execute('SELECT count(*) FROM cards WHERE owner=?', (owner,)).fetchone()[0] >= 500:
                raise RuntimeFailure('card_limit_exceeded', '最多保存 500 张经历卡，请先整理旧记录。')
            db.execute('INSERT INTO cards VALUES (?,?,?,?)', (owner, card['card_id'], 1, json.dumps(card, ensure_ascii=False)))
            db.execute('INSERT INTO receipts VALUES (?,?,?,?)', (owner, operation, fingerprint, card['card_id']))
            self._tick(db, owner)
        return card

    def change(self, owner, card_id, revision, *, remember=None, delete=False):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM cards WHERE owner=? AND id=?', (owner, card_id)).fetchone()
            if not row:
                raise RuntimeFailure('card_not_found', '经历卡不存在。', 404)
            if row['revision'] != revision:
                raise RuntimeFailure('stale_revision', '经历卡已变化，请刷新。')
            card = json.loads(row['payload'])
            if delete:
                db.execute('DELETE FROM cards WHERE owner=? AND id=?', (owner, card_id))
            else:
                card.update(remember_for_future=remember, revision=revision+1)
                db.execute('UPDATE cards SET revision=?,payload=? WHERE owner=? AND id=?', (revision+1, json.dumps(card, ensure_ascii=False), owner, card_id))
            self._tick(db, owner)
            return card

    def delete_owner(self, owner):
        with self.db() as db:
            for table in ('cards', 'receipts', 'memory_clock'):
                db.execute(f'DELETE FROM {table} WHERE owner=?', (owner,))
