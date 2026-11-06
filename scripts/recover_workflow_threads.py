import asyncio
import os

import psycopg
from dotenv import load_dotenv
from psycopg.rows import dict_row

from langgraph.checkpoint.postgres.aio import (
    AsyncPostgresSaver,
)


load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]


async def recover_case_thread(
    case_id: str,
) -> None:

    matches = []

    async with (
        AsyncPostgresSaver.from_conn_string(
            DATABASE_URL
        )
    ) as saver:

        async for checkpoint_tuple in saver.alist(
            None,
            limit=500,
        ):

            config = (
                checkpoint_tuple.config
                or {}
            )

            configurable = config.get(
                "configurable",
                {},
            )

            thread_id = configurable.get(
                "thread_id"
            )

            checkpoint = (
                checkpoint_tuple.checkpoint
                or {}
            )

            channel_values = (
                checkpoint.get(
                    "channel_values",
                    {},
                )
            )

            checkpoint_case_id = (
                channel_values.get(
                    "case_id"
                )
            )

            if checkpoint_case_id == case_id:
                matches.append(
                    {
                        "case_id": (
                            checkpoint_case_id
                        ),
                        "thread_id": (
                            thread_id
                        ),
                        "stage": (
                            channel_values.get(
                                "current_stage"
                            )
                        ),
                        "status": (
                            channel_values.get(
                                "status"
                            )
                        ),
                        "has_claim_data": (
                            "claim_data"
                            in channel_values
                        ),
                    }
                )

    if not matches:
        print(
            "No persisted checkpoint found "
            f"for {case_id}."
        )

        return

    print(
        f"Checkpoint candidates for {case_id}:"
    )

    for match in matches:
        print(match)

    usable_matches = [
        match
        for match in matches
        if match["thread_id"]
        and match["has_claim_data"]
    ]

    if not usable_matches:
        print(
            "Checkpoints were found, but none "
            "contains resumable claim_data."
        )

        return

    selected = usable_matches[0]

    print()
    print(
        "Selected thread:",
        selected["thread_id"],
    )

    with psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    ) as conn:

        with conn.cursor() as cur:

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS
                public.claim_workflow_threads
                (
                    case_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    created_at TIMESTAMPTZ
                        NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ
                        NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                INSERT INTO
                    public.claim_workflow_threads
                (
                    case_id,
                    thread_id
                )
                VALUES (%s, %s)
                ON CONFLICT (case_id)
                DO UPDATE SET
                    thread_id =
                        EXCLUDED.thread_id,
                    updated_at = NOW()
                """,
                (
                    case_id,
                    selected[
                        "thread_id"
                    ],
                ),
            )

        conn.commit()

    print(
        "Recovered workflow mapping "
        f"for {case_id}."
    )


async def main():

    case_id = "CASE-D5246C"

    await recover_case_thread(
        case_id
    )


if __name__ == "__main__":
    asyncio.run(main())