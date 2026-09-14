"""The worker's queue encoding. Pure — no database, no Redis.

ARQ pickles jobs by default and unpickles whatever it reads back, so anyone
able to write to its Redis queue could run code in the worker. These pin JSON.
"""

import pickle

import pytest

from app.worker.arq_worker import WorkerSettings, decode_job, encode_job


def test_the_worker_uses_the_json_codec():
    assert WorkerSettings.job_serializer is encode_job
    assert WorkerSettings.job_deserializer is decode_job


def test_a_cron_job_round_trips():
    job = {"t": 1, "f": "cron:dispatch_outbox", "a": (), "k": {}, "et": 1757970000000}

    assert decode_job(encode_job(job)) == {**job, "a": []}


def test_a_result_json_cannot_encode_becomes_text():
    """A failed job's exception must not stop ARQ recording the result."""
    decoded = decode_job(encode_job({"s": False, "r": ValueError("boom")}))

    assert decoded == {"s": False, "r": "boom"}


def test_a_pickled_payload_is_refused():
    with pytest.raises(ValueError):
        decode_job(pickle.dumps({"f": "anything"}))
