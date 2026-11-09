from unittest.mock import patch

import app.streamlit_app as streamlit_app


def test_recovers_missing_thread_id_from_langgraph_checkpoint(monkeypatch):
    saved = {}

    def fake_get_thread_id(case_id, create_if_missing=False):
        return None

    def fake_save_thread_id(case_id, thread_id):
        saved["value"] = (case_id, thread_id)

    class DummySaver:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def alist(self, *args, **kwargs):
            yield type(
                "CheckpointTuple",
                (),
                {
                    "config": {"configurable": {"thread_id": "CASE-42-THREAD-1"}},
                    "checkpoint": {"channel_values": {"case_id": "CASE-42", "status": "awaiting_human_review", "claim_data": {}}},
                },
            )()

    monkeypatch.setattr(streamlit_app, "_get_thread_id", fake_get_thread_id)
    monkeypatch.setattr(streamlit_app, "_save_thread_id", fake_save_thread_id)
    monkeypatch.setattr(streamlit_app.AsyncPostgresSaver, "from_conn_string", classmethod(lambda cls, *args, **kwargs: DummySaver()))

    recovered = streamlit_app._recover_thread_id_for_case("CASE-42")

    assert recovered == "CASE-42-THREAD-1"
    assert saved["value"] == ("CASE-42", "CASE-42-THREAD-1")


def test_recovers_latest_paused_thread_when_old_checkpoint_exists(monkeypatch):
    saved = {}

    def fake_get_thread_id(case_id, create_if_missing=False):
        return None

    def fake_save_thread_id(case_id, thread_id):
        saved["value"] = (case_id, thread_id)

    class DummySaver:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def alist(self, *args, **kwargs):
            yield type(
                "CheckpointTuple",
                (),
                {
                    "config": {"configurable": {"thread_id": "CASE-42-OLD"}},
                    "checkpoint": {"channel_values": {"case_id": "CASE-42", "status": "documents_complete", "current_stage": "documents_complete", "claim_data": {}}},
                },
            )()
            yield type(
                "CheckpointTuple",
                (),
                {
                    "config": {"configurable": {"thread_id": "CASE-42-NEW"}},
                    "checkpoint": {"channel_values": {"case_id": "CASE-42", "status": "awaiting_documents", "current_stage": "awaiting_documents", "claim_data": {}}},
                },
            )()

    monkeypatch.setattr(streamlit_app, "_get_thread_id", fake_get_thread_id)
    monkeypatch.setattr(streamlit_app, "_save_thread_id", fake_save_thread_id)
    monkeypatch.setattr(streamlit_app.AsyncPostgresSaver, "from_conn_string", classmethod(lambda cls, *args, **kwargs: DummySaver()))

    recovered = streamlit_app._recover_thread_id_for_case("CASE-42")

    assert recovered == "CASE-42-NEW"
    assert saved["value"] == ("CASE-42", "CASE-42-NEW")
