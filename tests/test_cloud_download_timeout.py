"""A Drive download is copied by Composio before it answers, so that one call waits up to 58 s; every other call keeps the usual limit."""
import asyncio

from app import cloud_storage as cloud
from hermes.services import composio_sessions as sessions


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_the_download_call_gets_the_long_timeout_and_it_is_released():
    seen = {}

    async def fake():
        seen["during"] = sessions.CALL_TIMEOUT.get()
        return "ok"

    assert run(cloud._timed("GOOGLEDRIVE_DOWNLOAD_FILE", fake())) == "ok"
    assert seen["during"] == cloud.DOWNLOAD_CALL_SECONDS == 58.0
    assert sessions.CALL_TIMEOUT.get() == 0.0


def test_other_calls_keep_the_usual_timeout():
    seen = {}

    async def fake():
        seen["during"] = sessions.CALL_TIMEOUT.get()

    run(cloud._timed("GOOGLEDRIVE_LIST_FILES", fake()))
    assert seen["during"] == 0.0
