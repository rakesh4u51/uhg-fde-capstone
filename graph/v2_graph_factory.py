from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from graph.workflow_v2 import builder
from services.database import DATABASE_URL


@asynccontextmanager
async def get_v2_graph() -> AsyncGenerator:
    async with AsyncPostgresSaver.from_conn_string(DATABASE_URL) as checkpointer:
        await checkpointer.setup()
        graph = builder.compile(checkpointer=checkpointer)
        yield graph
