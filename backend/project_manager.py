from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import uuid
from typing import Any, Dict, List, Optional

from database import (
    _table_columns,
    add_log,
    get_conn,
    get_local_targets_by_ids,
    get_segment,
    get_segment_target_count,
    get_segment_targets,
)

PROJECT_STATUS_READY = 'ready'
PROJECT_STATUS_RUNNING = 'running'
PROJECT_STATUS_PAUSED = 'paused'
PROJECT_STATUS_COMPLETED = 'completed'
PROJECT_STATUS_ARCHIVED = 'archived'
PROJECT_ACTIVE_STATUSES = {PROJECT_STATUS_READY, PROJECT_STATUS_RUNNING, PROJECT_STATUS_PAUSED}

PROJECT_TARGET_PENDING = '待发送'
PROJECT_TARGET_SENT = '已发送'
PROJECT_TARGET_REPLIED = '已回复'
PROJECT_TARGET_MANUAL = '人工接管'
PROJECT_TARGET_COMPLETED = '完成'
PROJECT_TARGET_SKIPPED = '跳过'
PROJECT_TARGET_CANNOT_DM = '不可DM'
DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS = 3
DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS = 5


@dataclass
class Project:
    id: str
    name: str
    client_group: str = ''
    description: str = ''
    status: str = PROJECT_STATUS_READY
    segment_id: str = ''
    segment_name: str = ''
    template_id: str = ''
    followup_template_id: str = ''
    sequence_step_1_template_id: str = ''
    sequence_step_2_template_id: str = ''
    sequence_step_3_template_id: str = ''
    sequence_step_2_delay_days: int = DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS
    sequence_step_3_delay_days: int = DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS
    sequence_step_2_enabled: bool = True
    sequence_step_3_enabled: bool = True
    created_at: str = ''
    updated_at: str = ''
    last_run_at: str = ''
    total_targets: int = 0
    pending_count: int = 0
    sent_count: int = 0
    replied_count: int = 0
    manual_takeover_count: int = 0
    completed_count: int = 0
    warming_enabled: bool = False
    followup_enabled: bool = True


PROJECT_COLUMNS: Dict[str, str] = {
    'client_group': "TEXT DEFAULT ''",
    'description': "TEXT DEFAULT ''",
    'status': f"TEXT DEFAULT '{PROJECT_STATUS_READY}'",
    'segment_id': "TEXT DEFAULT ''",
    'segment_name': "TEXT DEFAULT ''",
    'template_id': "TEXT DEFAULT ''",
    'followup_template_id': "TEXT DEFAULT ''",
    'sequence_step_1_template_id': "TEXT DEFAULT ''",
    'sequence_step_2_template_id': "TEXT DEFAULT ''",
    'sequence_step_3_template_id': "TEXT DEFAULT ''",
    'sequence_step_2_delay_days': f'INTEGER DEFAULT {DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS}',
    'sequence_step_3_delay_days': f'INTEGER DEFAULT {DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS}',
    'sequence_step_2_enabled': 'INTEGER DEFAULT 1',
    'sequence_step_3_enabled': 'INTEGER DEFAULT 1',
    'last_run_at': "TEXT DEFAULT ''",
    'total_targets': 'INTEGER DEFAULT 0',
    'pending_count': 'INTEGER DEFAULT 0',
    'sent_count': 'INTEGER DEFAULT 0',
    'replied_count': 'INTEGER DEFAULT 0',
    'manual_takeover_count': 'INTEGER DEFAULT 0',
    'completed_count': 'INTEGER DEFAULT 0',
    'warming_enabled': 'INTEGER DEFAULT 0',
    'followup_enabled': 'INTEGER DEFAULT 1',
}

PROJECT_TARGET_COLUMNS: Dict[str, str] = {
    'id': 'TEXT PRIMARY KEY',
    'project_id': 'TEXT NOT NULL',
    'target_id': 'TEXT NOT NULL',
    'target_source': "TEXT DEFAULT 'local'",
    'twitter_username': 'TEXT NOT NULL',
    'target_type': "TEXT DEFAULT ''",
    'priority': "TEXT DEFAULT ''",
    'status': f"TEXT DEFAULT '{PROJECT_TARGET_PENDING}'",
    'source_segment_id': "TEXT DEFAULT ''",
    'source_segment_name': "TEXT DEFAULT ''",
    'client_group': "TEXT DEFAULT ''",
    'client_note': "TEXT DEFAULT ''",
    'sent_by': "TEXT DEFAULT ''",
    'sent_time': "TEXT DEFAULT ''",
    'fail_reason': "TEXT DEFAULT ''",
    'reply_content': "TEXT DEFAULT ''",
    'has_reply': 'INTEGER DEFAULT 0',
    'reply_at': "TEXT DEFAULT ''",
    'conversation_id': "TEXT DEFAULT ''",
    'contact_count': 'INTEGER DEFAULT 0',
    'last_contact_time': "TEXT DEFAULT ''",
    'created_at': 'TEXT',
    'updated_at': 'TEXT',
}

PROJECT_ACCOUNT_COLUMNS: Dict[str, str] = {
    'project_id': 'TEXT NOT NULL',
    'account_id': 'TEXT NOT NULL',
    'priority': 'INTEGER DEFAULT 0',
    'status': "TEXT DEFAULT 'active'",
    'added_at': 'TEXT',
}


def _ensure_column(conn, table: str, name: str, col_def: str) -> None:
    if name in _table_columns(conn, table):
        return
    conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {col_def}')


def _new_id(prefix: str) -> str:
    return f'{prefix}_{uuid.uuid4().hex[:10]}'


def init_project_tables() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                client_group TEXT DEFAULT '',
                description TEXT DEFAULT '',
                status TEXT DEFAULT 'ready',
                segment_id TEXT DEFAULT '',
                segment_name TEXT DEFAULT '',
                template_id TEXT DEFAULT '',
                followup_template_id TEXT DEFAULT '',
                sequence_step_1_template_id TEXT DEFAULT '',
                sequence_step_2_template_id TEXT DEFAULT '',
                sequence_step_3_template_id TEXT DEFAULT '',
                sequence_step_2_delay_days INTEGER DEFAULT 3,
                sequence_step_3_delay_days INTEGER DEFAULT 5,
                sequence_step_2_enabled INTEGER DEFAULT 1,
                sequence_step_3_enabled INTEGER DEFAULT 1,
                last_run_at TEXT DEFAULT '',
                total_targets INTEGER DEFAULT 0,
                pending_count INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                replied_count INTEGER DEFAULT 0,
                manual_takeover_count INTEGER DEFAULT 0,
                completed_count INTEGER DEFAULT 0,
                warming_enabled INTEGER DEFAULT 0,
                followup_enabled INTEGER DEFAULT 1,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        for name, col_def in PROJECT_COLUMNS.items():
            _ensure_column(conn, 'projects', name, col_def)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_accounts (
                project_id TEXT NOT NULL,
                account_id TEXT NOT NULL,
                priority INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                added_at TEXT,
                PRIMARY KEY (project_id, account_id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS project_targets (
                id TEXT PRIMARY KEY,
                project_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                target_source TEXT DEFAULT 'local',
                twitter_username TEXT NOT NULL,
                target_type TEXT DEFAULT '',
                priority TEXT DEFAULT '',
                status TEXT DEFAULT '待发送',
                source_segment_id TEXT DEFAULT '',
                source_segment_name TEXT DEFAULT '',
                client_group TEXT DEFAULT '',
                client_note TEXT DEFAULT '',
                sent_by TEXT DEFAULT '',
                sent_time TEXT DEFAULT '',
                fail_reason TEXT DEFAULT '',
                reply_content TEXT DEFAULT '',
                has_reply INTEGER DEFAULT 0,
                reply_at TEXT DEFAULT '',
                conversation_id TEXT DEFAULT '',
                contact_count INTEGER DEFAULT 0,
                last_contact_time TEXT DEFAULT '',
                created_at TEXT,
                updated_at TEXT,
                UNIQUE(project_id, target_id, target_source)
            )
            """
        )
        conn.execute('CREATE INDEX IF NOT EXISTS idx_project_targets_project ON project_targets(project_id, status)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_project_targets_target ON project_targets(target_id, target_source)')


init_project_tables()


def _row_to_project(row: Dict[str, Any]) -> Project:
    template_id = str(row.get('template_id') or '')
    followup_template_id = str(row.get('followup_template_id') or '')
    followup_enabled = bool(int(row.get('followup_enabled') or 0))
    step_1_template_id = str(row.get('sequence_step_1_template_id') or template_id)
    step_2_template_id = str(row.get('sequence_step_2_template_id') or followup_template_id)
    step_3_template_id = str(row.get('sequence_step_3_template_id') or followup_template_id)
    step_2_enabled_raw = row.get('sequence_step_2_enabled')
    step_3_enabled_raw = row.get('sequence_step_3_enabled')
    step_2_enabled = bool(int(step_2_enabled_raw)) if step_2_enabled_raw is not None else followup_enabled
    step_3_enabled = bool(int(step_3_enabled_raw)) if step_3_enabled_raw is not None else followup_enabled
    return Project(
        id=str(row.get('id') or ''),
        name=str(row.get('name') or ''),
        client_group=str(row.get('client_group') or ''),
        description=str(row.get('description') or ''),
        status=str(row.get('status') or PROJECT_STATUS_READY),
        segment_id=str(row.get('segment_id') or ''),
        segment_name=str(row.get('segment_name') or ''),
        template_id=template_id,
        followup_template_id=followup_template_id,
        sequence_step_1_template_id=step_1_template_id,
        sequence_step_2_template_id=step_2_template_id,
        sequence_step_3_template_id=step_3_template_id,
        sequence_step_2_delay_days=max(1, int(row.get('sequence_step_2_delay_days') or DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS)),
        sequence_step_3_delay_days=max(1, int(row.get('sequence_step_3_delay_days') or DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS)),
        sequence_step_2_enabled=step_2_enabled,
        sequence_step_3_enabled=step_3_enabled,
        created_at=str(row.get('created_at') or ''),
        updated_at=str(row.get('updated_at') or ''),
        last_run_at=str(row.get('last_run_at') or ''),
        total_targets=int(row.get('total_targets') or 0),
        pending_count=int(row.get('pending_count') or 0),
        sent_count=int(row.get('sent_count') or 0),
        replied_count=int(row.get('replied_count') or 0),
        manual_takeover_count=int(row.get('manual_takeover_count') or 0),
        completed_count=int(row.get('completed_count') or 0),
        warming_enabled=bool(int(row.get('warming_enabled') or 0)),
        followup_enabled=followup_enabled,
    )


def get_project(project_id: str) -> Optional[Project]:
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM projects WHERE id = ?', (str(project_id or '').strip(),)).fetchone()
    return _row_to_project(dict(row)) if row else None


def list_projects(status: Optional[str] = None) -> List[Project]:
    sql = 'SELECT * FROM projects'
    params: List[Any] = []
    if status:
        sql += ' WHERE status = ?'
        params.append(str(status))
    sql += ' ORDER BY updated_at DESC, created_at DESC'
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_row_to_project(dict(row)) for row in rows]


def get_project_map(project_ids: List[str]) -> Dict[str, Project]:
    ids = [str(x).strip() for x in project_ids if str(x).strip()]
    if not ids:
        return {}
    placeholders = ','.join('?' for _ in ids)
    with get_conn() as conn:
        rows = conn.execute(f'SELECT * FROM projects WHERE id IN ({placeholders})', ids).fetchall()
    return {str(row['id']): _row_to_project(dict(row)) for row in rows}


def list_project_account_links(project_id: str) -> List[Dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM project_accounts WHERE project_id = ? ORDER BY priority ASC, added_at ASC',
            (str(project_id or '').strip(),),
        ).fetchall()
    return [dict(row) for row in rows]


def get_project_accounts(project_id: str) -> List[Dict[str, Any]]:
    return list_project_account_links(project_id)


def upsert_project_accounts(project_id: str, account_ids: List[str]) -> int:
    now = datetime.now().isoformat(timespec='seconds')
    clean_ids = [str(x).strip() for x in account_ids if str(x).strip()]
    with get_conn() as conn:
        conn.execute('DELETE FROM project_accounts WHERE project_id = ?', (project_id,))
        for idx, account_id in enumerate(clean_ids):
            conn.execute(
                """
                INSERT OR REPLACE INTO project_accounts (project_id, account_id, priority, status, added_at)
                VALUES (?, ?, ?, 'active', ?)
                """,
                (project_id, account_id, idx, now),
            )
    return len(clean_ids)


def _segment_snapshot(segment_id: str) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    segment = get_segment(segment_id) or {}
    total = get_segment_target_count(segment_id)
    page = 1
    page_size = 200
    rows: List[Dict[str, Any]] = []
    while len(rows) < total:
        batch = get_segment_targets(segment_id, page=page, page_size=page_size)
        if not batch:
            break
        rows.extend(batch)
        page += 1
    return segment, rows


def _project_target_payload(project: Project, row: Dict[str, Any], local_map: Dict[str, Dict[str, Any]], feishu_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    target_id = str(row.get('target_id') or '').strip()
    target_source = str(row.get('target_source') or 'local').strip() or 'local'
    base = local_map.get(target_id, {}) if target_source == 'local' else feishu_map.get(target_id, {})
    twitter_username = str(base.get('twitter_username') or row.get('twitter_username') or '').replace('@', '').strip()
    return {
        'id': _new_id('ptgt'),
        'project_id': project.id,
        'target_id': target_id,
        'target_source': target_source,
        'twitter_username': twitter_username,
        'target_type': str(base.get('type') or ''),
        'priority': str(base.get('priority') or ''),
        'status': PROJECT_TARGET_PENDING,
        'source_segment_id': project.segment_id,
        'source_segment_name': project.segment_name,
        'client_group': project.client_group,
        'client_note': str(base.get('client_note') or ''),
        'sent_by': '',
        'sent_time': '',
        'fail_reason': '',
        'reply_content': '',
        'has_reply': 0,
        'reply_at': '',
        'conversation_id': '',
        'contact_count': 0,
        'last_contact_time': '',
    }


def sync_project_targets_from_segment(project_id: str) -> int:
    project = get_project(project_id)
    if not project or not project.segment_id:
        return 0

    segment, rows = _segment_snapshot(project.segment_id)
    if not project.segment_name and segment:
        with get_conn() as conn:
            conn.execute(
                'UPDATE projects SET segment_name = ?, updated_at = ? WHERE id = ?',
                (str(segment.get('name') or ''), datetime.now().isoformat(timespec='seconds'), project_id),
            )
        project.segment_name = str(segment.get('name') or '')

    local_ids = [str(row.get('target_id') or '') for row in rows if str(row.get('target_source') or 'local') == 'local']
    local_map = {str(item.get('id')): item for item in get_local_targets_by_ids(local_ids)}

    feishu_map: Dict[str, Dict[str, Any]] = {}
    feishu_ids = [str(row.get('target_id') or '') for row in rows if str(row.get('target_source') or 'local') != 'local']
    if feishu_ids:
        try:
            from feishu import get_all_targets, get_token
            token = get_token()
            feishu_map = {str(item.get('record_id')): item for item in get_all_targets(token) if str(item.get('record_id')) in feishu_ids}
        except Exception:
            feishu_map = {}

    now = datetime.now().isoformat(timespec='seconds')
    inserted = 0
    with get_conn() as conn:
        for row in rows:
            payload = _project_target_payload(project, row, local_map, feishu_map)
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO project_targets (
                    id, project_id, target_id, target_source, twitter_username, target_type, priority,
                    status, source_segment_id, source_segment_name, client_group, client_note,
                    sent_by, sent_time, fail_reason, reply_content, has_reply, reply_at,
                    conversation_id, contact_count, last_contact_time, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload['id'], payload['project_id'], payload['target_id'], payload['target_source'], payload['twitter_username'],
                    payload['target_type'], payload['priority'], payload['status'], payload['source_segment_id'], payload['source_segment_name'],
                    payload['client_group'], payload['client_note'], payload['sent_by'], payload['sent_time'], payload['fail_reason'],
                    payload['reply_content'], payload['has_reply'], payload['reply_at'], payload['conversation_id'], payload['contact_count'],
                    payload['last_contact_time'], now, now,
                ),
            )
            if int(cur.rowcount or 0) > 0:
                inserted += 1
    refresh_project_stats(project_id)
    return inserted


def create_project(
    name: str,
    description: str = '',
    client_group: str = '',
    segment_id: str = '',
    template_id: str = '',
    followup_template_id: str = '',
    sequence_step_1_template_id: str = '',
    sequence_step_2_template_id: str = '',
    sequence_step_3_template_id: str = '',
    sequence_step_2_delay_days: int = DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS,
    sequence_step_3_delay_days: int = DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS,
    sequence_step_2_enabled: bool = True,
    sequence_step_3_enabled: bool = True,
    account_ids: Optional[List[str]] = None,
    warming_enabled: bool = False,
    followup_enabled: bool = True,
) -> Project:
    now = datetime.now().isoformat(timespec='seconds')
    project_id = _new_id('proj')
    segment = get_segment(segment_id) if segment_id else None
    segment_name = str((segment or {}).get('name') or '')

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, name, client_group, description, status, segment_id, segment_name,
                template_id, followup_template_id,
                sequence_step_1_template_id, sequence_step_2_template_id, sequence_step_3_template_id,
                sequence_step_2_delay_days, sequence_step_3_delay_days,
                sequence_step_2_enabled, sequence_step_3_enabled,
                last_run_at,
                total_targets, pending_count, sent_count, replied_count, manual_takeover_count, completed_count,
                warming_enabled, followup_enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, 0, 0, 0, 0, ?, ?, ?, ?)
            """,
            (
                project_id,
                str(name or '').strip(),
                str(client_group or '').strip(),
                str(description or '').strip(),
                PROJECT_STATUS_READY,
                str(segment_id or '').strip(),
                segment_name,
                str(template_id or '').strip(),
                str(followup_template_id or '').strip(),
                str(sequence_step_1_template_id or template_id or '').strip(),
                str(sequence_step_2_template_id or followup_template_id or '').strip(),
                str(sequence_step_3_template_id or followup_template_id or '').strip(),
                max(1, int(sequence_step_2_delay_days or DEFAULT_SEQUENCE_STEP_2_DELAY_DAYS)),
                max(1, int(sequence_step_3_delay_days or DEFAULT_SEQUENCE_STEP_3_DELAY_DAYS)),
                int(bool(sequence_step_2_enabled)),
                int(bool(sequence_step_3_enabled)),
                int(bool(warming_enabled)),
                int(bool(followup_enabled)),
                now,
                now,
            ),
        )

    upsert_project_accounts(project_id, account_ids or [])
    if segment_id:
        sync_project_targets_from_segment(project_id)
    refresh_project_stats(project_id)
    add_log('INFO', 'system', '', 'project_created', f'项目已创建：{name}')
    return get_project(project_id) or Project(id=project_id, name=name)


def refresh_project_stats(project_id: str) -> Optional[Project]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS cnt
            FROM project_targets
            WHERE project_id = ?
            GROUP BY status
            """,
            (str(project_id or '').strip(),),
        ).fetchall()
        counts = {str(row['status']): int(row['cnt']) for row in rows}
        total = sum(counts.values())
        pending_count = counts.get(PROJECT_TARGET_PENDING, 0)
        sent_count = counts.get(PROJECT_TARGET_SENT, 0)
        replied_count = counts.get(PROJECT_TARGET_REPLIED, 0)
        manual_count = counts.get(PROJECT_TARGET_MANUAL, 0)
        completed_count = counts.get(PROJECT_TARGET_COMPLETED, 0)

        next_status = None
        current = conn.execute('SELECT status FROM projects WHERE id = ?', (project_id,)).fetchone()
        if current and str(current['status']) not in {PROJECT_STATUS_ARCHIVED, PROJECT_STATUS_PAUSED}:
            if total > 0 and pending_count == 0 and sent_count == 0 and manual_count == 0:
                next_status = PROJECT_STATUS_COMPLETED if (replied_count + completed_count) > 0 else PROJECT_STATUS_RUNNING
            elif str(current['status']) != PROJECT_STATUS_RUNNING and total > 0:
                next_status = str(current['status'])
            else:
                next_status = str(current['status'])

        conn.execute(
            """
            UPDATE projects
            SET total_targets = ?, pending_count = ?, sent_count = ?, replied_count = ?,
                manual_takeover_count = ?, completed_count = ?,
                status = COALESCE(?, status), updated_at = ?
            WHERE id = ?
            """,
            (
                total,
                pending_count,
                sent_count,
                replied_count,
                manual_count,
                completed_count,
                next_status,
                datetime.now().isoformat(timespec='seconds'),
                project_id,
            ),
        )
    return get_project(project_id)


def get_project_targets(project_id: str, status: Optional[str] = None, limit: int = 500) -> List[Dict[str, Any]]:
    sql = 'SELECT * FROM project_targets WHERE project_id = ?'
    params: List[Any] = [str(project_id or '').strip()]
    if status:
        sql += ' AND status = ?'
        params.append(str(status))
    sql += ' ORDER BY updated_at DESC LIMIT ?'
    params.append(max(1, int(limit or 500)))
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def get_project_target(project_target_id: str) -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute('SELECT * FROM project_targets WHERE id = ?', (str(project_target_id or '').strip(),)).fetchone()
    return dict(row) if row else None


def resolve_project_targets(project_id: str, status: str = PROJECT_TARGET_PENDING) -> List[Dict[str, Any]]:
    project = get_project(project_id)
    if not project:
        return []
    rows = get_project_targets(project_id, status=status, limit=2000)
    if not rows:
        return []

    local_ids = [str(row.get('target_id') or '') for row in rows if str(row.get('target_source') or 'local') == 'local']
    local_map = {str(item.get('id')): item for item in get_local_targets_by_ids(local_ids)}

    feishu_map: Dict[str, Dict[str, Any]] = {}
    feishu_ids = [str(row.get('target_id') or '') for row in rows if str(row.get('target_source') or 'local') != 'local']
    if feishu_ids:
        try:
            from feishu import get_all_targets, get_token
            token = get_token()
            feishu_map = {str(item.get('record_id')): item for item in get_all_targets(token) if str(item.get('record_id')) in feishu_ids}
        except Exception:
            feishu_map = {}

    resolved: List[Dict[str, Any]] = []
    for row in rows:
        target_id = str(row.get('target_id') or '')
        target_source = str(row.get('target_source') or 'local') or 'local'
        base = local_map.get(target_id, {}) if target_source == 'local' else feishu_map.get(target_id, {})
        username = str(base.get('twitter_username') or row.get('twitter_username') or '').replace('@', '').strip()
        if not username:
            continue
        resolved.append(
            {
                **base,
                'record_id': target_id,
                '_source': target_source,
                'twitter_username': username,
                'type': str(base.get('type') or row.get('target_type') or ''),
                'priority': str(base.get('priority') or row.get('priority') or ''),
                'project_name': project.name,
                'project_id': project.id,
                'project_target_id': str(row.get('id') or ''),
                'client_group': project.client_group or str(row.get('client_group') or ''),
                'client_note': str(row.get('client_note') or ''),
                'segment_id': project.segment_id,
                'segment_name': project.segment_name,
                'template_id': project.template_id,
                'followup_template_id': project.followup_template_id,
                'sequence_step_1_template_id': project.sequence_step_1_template_id,
                'sequence_step_2_template_id': project.sequence_step_2_template_id,
                'sequence_step_3_template_id': project.sequence_step_3_template_id,
                'sequence_step_2_delay_days': project.sequence_step_2_delay_days,
                'sequence_step_3_delay_days': project.sequence_step_3_delay_days,
                'sequence_step_2_enabled': project.sequence_step_2_enabled,
                'sequence_step_3_enabled': project.sequence_step_3_enabled,
                'followup_enabled': project.followup_enabled,
                'warming_enabled': project.warming_enabled,
            }
        )
    return resolved


def update_project_status(project_id: str, status: str) -> None:
    with get_conn() as conn:
        conn.execute(
            'UPDATE projects SET status = ?, updated_at = ? WHERE id = ?',
            (str(status), datetime.now().isoformat(timespec='seconds'), str(project_id or '').strip()),
        )


def pause_project(project_id: str) -> Optional[Project]:
    update_project_status(project_id, PROJECT_STATUS_PAUSED)
    add_log('INFO', 'system', '', 'project_paused', f'项目已暂停：{project_id}')
    return get_project(project_id)


def resume_project(project_id: str) -> Optional[Project]:
    update_project_status(project_id, PROJECT_STATUS_RUNNING)
    add_log('INFO', 'system', '', 'project_resumed', f'项目已恢复：{project_id}')
    return get_project(project_id)


def archive_project(project_id: str) -> Optional[Project]:
    update_project_status(project_id, PROJECT_STATUS_ARCHIVED)
    add_log('INFO', 'system', '', 'project_archived', f'项目已归档：{project_id}')
    return get_project(project_id)


def is_project_send_enabled(project_id: str) -> bool:
    project = get_project(project_id)
    return bool(project and project.status == PROJECT_STATUS_RUNNING)


def mark_project_target_sent(
    project_target_id: str,
    status: str,
    sent_by: str = '',
    fail_reason: str = '',
    reply_content: str = '',
    conversation_id: str = '',
) -> Optional[Dict[str, Any]]:
    row = get_project_target(project_target_id)
    if not row:
        return None
    now = datetime.now().isoformat(timespec='seconds')
    next_contact_count = int(row.get('contact_count') or 0)
    if status == PROJECT_TARGET_SENT:
        next_contact_count += 1
    payload = {
        'status': status,
        'sent_by': str(sent_by or row.get('sent_by') or ''),
        'sent_time': now if status == PROJECT_TARGET_SENT else str(row.get('sent_time') or ''),
        'fail_reason': str(fail_reason or ''),
        'reply_content': str(reply_content or row.get('reply_content') or ''),
        'conversation_id': str(conversation_id or row.get('conversation_id') or ''),
        'contact_count': next_contact_count,
        'last_contact_time': now if status == PROJECT_TARGET_SENT else str(row.get('last_contact_time') or ''),
        'updated_at': now,
    }
    set_clause = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [project_target_id]
    with get_conn() as conn:
        conn.execute(f'UPDATE project_targets SET {set_clause} WHERE id = ?', values)
    refresh_project_stats(str(row.get('project_id') or ''))
    return get_project_target(project_target_id)


def mark_project_target_replied(
    project_target_id: str,
    reply_preview: str,
    reply_at: str = '',
    conversation_id: str = '',
) -> Optional[Dict[str, Any]]:
    row = get_project_target(project_target_id)
    if not row:
        return None
    now = reply_at or datetime.now().isoformat(timespec='seconds')
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE project_targets
            SET status = ?, has_reply = 1, reply_at = ?, reply_content = ?,
                conversation_id = CASE WHEN ? != '' THEN ? ELSE conversation_id END,
                updated_at = ?
            WHERE id = ?
            """,
            (
                PROJECT_TARGET_REPLIED,
                now,
                str(reply_preview or '')[:500],
                str(conversation_id or ''),
                str(conversation_id or ''),
                datetime.now().isoformat(timespec='seconds'),
                project_target_id,
            ),
        )
    refresh_project_stats(str(row.get('project_id') or ''))
    return get_project_target(project_target_id)


def set_project_target_status(project_target_id: str, status: str, note: str = '') -> Optional[Dict[str, Any]]:
    row = get_project_target(project_target_id)
    if not row:
        return None
    payload = {
        'status': str(status),
        'updated_at': datetime.now().isoformat(timespec='seconds'),
    }
    if note:
        payload['reply_content'] = str(note)[:500]
    set_clause = ', '.join(f'{key} = ?' for key in payload)
    values = list(payload.values()) + [project_target_id]
    with get_conn() as conn:
        conn.execute(f'UPDATE project_targets SET {set_clause} WHERE id = ?', values)
    refresh_project_stats(str(row.get('project_id') or ''))
    return get_project_target(project_target_id)


def get_project_target_by_source(target_id: str, target_source: str = 'local') -> Optional[Dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT * FROM project_targets
            WHERE target_id = ? AND target_source = ?
              AND status IN ('待发送', '已发送', '已回复', '人工接管')
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (str(target_id or '').strip(), str(target_source or 'local').strip() or 'local'),
        ).fetchone()
    return dict(row) if row else None


def get_project_detail(project_id: str) -> Optional[Dict[str, Any]]:
    project = get_project(project_id)
    if not project:
        return None
    return {
        'project': project,
        'accounts': get_project_accounts(project_id),
        'targets': get_project_targets(project_id, limit=1000),
    }


def start_project_sending(project_id: str, wait_between: bool = False) -> Dict[str, Any]:
    project = get_project(project_id)
    if not project:
        return {'ok': False, 'error': '项目不存在'}
    if project.status == PROJECT_STATUS_ARCHIVED:
        return {'ok': False, 'error': '项目已归档，无法启动'}

    if not list_project_account_links(project_id):
        return {'ok': False, 'error': '项目未分配账号'}
    if not get_project_targets(project_id, status=PROJECT_TARGET_PENDING, limit=1):
        refresh_project_stats(project_id)
        return {'ok': False, 'error': '项目内没有待发送目标'}

    from scheduler import get_status, resume, run_batch_for_project, start

    system_status = get_status()
    try:
        if not system_status.get('running'):
            start()
        elif system_status.get('paused'):
            resume()
    except RuntimeError as exc:
        return {'ok': False, 'error': str(exc)}

    update_project_status(project_id, PROJECT_STATUS_RUNNING)
    with get_conn() as conn:
        conn.execute(
            'UPDATE projects SET last_run_at = ?, updated_at = ? WHERE id = ?',
            (
                datetime.now().isoformat(timespec='seconds'),
                datetime.now().isoformat(timespec='seconds'),
                project_id,
            ),
        )

    import threading

    thread = threading.Thread(
        target=lambda: run_batch_for_project(project_id=project_id, wait_between=wait_between),
        daemon=True,
    )
    thread.start()
    add_log('INFO', 'system', '', 'project_start', f'项目已启动：{project.name}')
    return {
        'ok': True,
        'message': f'项目 {project.name} 已启动',
        'project_id': project.id,
    }
