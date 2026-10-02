import os
import psycopg
from psycopg.rows import dict_row
async def save_note(
    filename: str,
    language_code: str,
    transcript: str,
    audio_path: str,
):
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO audio_notes (
                    filename, language_code, transcript, audio_path
                )
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (filename, language_code, transcript, audio_path),
            )
            row = await cursor.fetchone()

    return str(row[0])
async def update_note_summary(note_id: str, summary: str):
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                UPDATE audio_notes
                SET summary = %s
                WHERE id = %s
                """,
                (summary, note_id),
            )
async def list_notes():
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        cursor = await conn.execute(
            """
            SELECT id, filename, language_code,
                   status, error_message,
                   created_at, updated_at
            FROM audio_notes
            ORDER BY created_at DESC, id DESC
            LIMIT 50
            """
        )
        return await cursor.fetchall()


async def get_note(note_id: str):
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        cursor = await conn.execute(
            """
            SELECT id, filename, language_code,
                   transcript, summary,
                   status, error_message,
                   created_at, updated_at
            FROM audio_notes
            WHERE id = %s
            """,
            (note_id,),
        )
        return await cursor.fetchone()
async def create_queued_note(
    filename: str,
    language_code: str,
    audio_path: str,
):
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute(
                """
                INSERT INTO audio_notes (
                    filename,
                    language_code,
                    audio_path,
                    status
                )
                VALUES (%s, %s, %s, 'queued')
                RETURNING id
                """,
                (filename, language_code, audio_path),
            )
            row = await cursor.fetchone()

    return str(row[0])


async def fail_note(
    note_id: str,
    claim_token: str,
    error_message: str,
) -> bool:
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        cursor = await conn.execute(
            """
            UPDATE audio_notes
            SET status = 'failed',
                error_message = %s,
                claim_token = NULL,
                lease_expires_at = NULL,
                updated_at = NOW()
            WHERE id = %s
              AND claim_token = %s
              AND lease_expires_at > NOW()
              AND status IN ('transcribing', 'summarizing')
            RETURNING id
            """,
            (error_message, note_id, claim_token),
        )
        updated = await cursor.fetchone()

    return updated is not None


async def save_note_transcript(
    note_id: str,
    claim_token: str,
    transcript: str,
) -> bool:
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        cursor = await conn.execute(
            """
            UPDATE audio_notes
            SET transcript = %s,
                status = 'summarizing',
                error_message = NULL,
                updated_at = NOW()
            WHERE id = %s
              AND claim_token = %s
              AND lease_expires_at > NOW()
              AND status = 'transcribing'
            RETURNING id
            """,
            (transcript, note_id, claim_token),
        )
        updated = await cursor.fetchone()

    return updated is not None
async def claim_next_note():
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
        row_factory=dict_row,
    ) as conn:
        cursor = await conn.execute(
            """
            WITH next_note AS (
                SELECT id
                FROM audio_notes
                WHERE status = 'queued'
                   OR (
                       status IN ('transcribing', 'summarizing')
                       AND (
                           lease_expires_at IS NULL
                           OR lease_expires_at <= NOW()
                       )
                   )
                ORDER BY created_at ASC, id ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            UPDATE audio_notes AS note
            SET status = CASE
                    WHEN note.transcript IS NULL
                        THEN 'transcribing'
                    ELSE 'summarizing'
                END,
                claim_token = gen_random_uuid(),
                lease_expires_at = NOW() + INTERVAL '5 minutes',
                error_message = NULL,
                updated_at = NOW()
            FROM next_note
            WHERE note.id = next_note.id
            RETURNING
    note.id,
    note.filename,
    note.language_code,
    note.audio_path,
    note.transcript,
    note.status,
    note.claim_token,
    note.gnani_job_id
            """
        )
        note = await cursor.fetchone()

    return note
async def renew_note_claim(
    note_id: str,
    claim_token: str,
) -> bool:
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        cursor = await conn.execute(
            """
            UPDATE audio_notes
            SET lease_expires_at = NOW() + INTERVAL '5 minutes',
                updated_at = NOW()
            WHERE id = %s
              AND claim_token = %s
              AND lease_expires_at > NOW()
              AND status IN ('transcribing', 'summarizing')
            RETURNING id
            """,
            (note_id, claim_token),
        )
        renewed = await cursor.fetchone()

    return renewed is not None
async def complete_note(
    note_id: str,
    claim_token: str,
    summary: str | None,
    error_message: str | None = None,
) -> bool:
    if not summary and not error_message:
        raise ValueError(
            "Provide a summary or explain why summarization failed."
        )

    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        cursor = await conn.execute(
            """
            UPDATE audio_notes
            SET summary = %s,
                status = 'completed',
                error_message = %s,
                claim_token = NULL,
                lease_expires_at = NULL,
                updated_at = NOW()
            WHERE id = %s
              AND claim_token = %s
              AND lease_expires_at > NOW()
              AND status = 'summarizing'
            RETURNING id
            """,
            (summary, error_message, note_id, claim_token),
        )
        updated = await cursor.fetchone()

    return updated is not None
async def save_gnani_job_id(
    note_id: str,
    claim_token: str,
    gnani_job_id: str,
) -> bool:
    async with await psycopg.AsyncConnection.connect(
        os.environ["DATABASE_URL"],
        connect_timeout=5,
    ) as conn:
        cursor = await conn.execute(
            """
            UPDATE audio_notes
            SET gnani_job_id = %s,
                updated_at = NOW()
            WHERE id = %s
              AND claim_token = %s
              AND lease_expires_at > NOW()
              AND status = 'transcribing'
              AND (
                  gnani_job_id IS NULL
                  OR gnani_job_id = %s
              )
            RETURNING id
            """,
            (
                gnani_job_id,
                note_id,
                claim_token,
                gnani_job_id,
            ),
        )
        updated = await cursor.fetchone()

    return updated is not None