"""Unit tests for TokenBucket and TokenBucketManager.

Real time-based and threading tests per Anti-Mock principles.
"""

import time
import threading
import pytest


def test_token_bucket_initial_capacity():
    from code_indexer.server.auth.token_bucket import TokenBucket

    b = TokenBucket(capacity=10, refill_rate=1 / 6)
    assert b.capacity == 10
    # Immediately after creation, tokens should equal capacity
    allowed, retry_after = b.consume()
    assert allowed is True
    assert retry_after == 0
    assert b.tokens == pytest.approx(9.0, rel=0.01, abs=0.05)


def test_token_bucket_consume_until_empty_then_block():
    from code_indexer.server.auth.token_bucket import TokenBucket

    b = TokenBucket(capacity=10, refill_rate=1 / 6)
    # consume 10 tokens allowed
    for _ in range(10):
        allowed, retry_after = b.consume()
        assert allowed is True
        assert retry_after == 0
    # 11th total attempt should be blocked
    allowed, retry_after = b.consume()
    assert allowed is False
    assert 5.5 <= retry_after <= 6.5


def test_token_bucket_refill_over_time():
    from code_indexer.server.auth.token_bucket import TokenBucket

    b = TokenBucket(capacity=10, refill_rate=1 / 6)
    # drain all tokens
    for _ in range(10):
        assert b.consume()[0] is True
    # next should be blocked
    allowed, retry_after = b.consume()
    assert allowed is False
    assert retry_after > 0

    # wait for one token to refill (1 token per 6s)
    time.sleep(6.2)
    allowed, retry_after = b.consume()
    assert allowed is True
    assert retry_after == 0


def test_manager_per_user_isolation():
    from code_indexer.server.auth.token_bucket import TokenBucketManager

    m = TokenBucketManager(capacity=5, refill_rate=1 / 6)
    # consume 5 for user A
    for _ in range(5):
        assert m.consume("userA")[0] is True
    # 6th should block for A
    allowed, _ = m.consume("userA")
    assert allowed is False

    # user B should be unaffected
    for _ in range(5):
        assert m.consume("userB")[0] is True


def test_manager_thread_safety_allows_only_capacity():
    from code_indexer.server.auth.token_bucket import TokenBucketManager

    m = TokenBucketManager(capacity=10, refill_rate=1 / 6)

    allowed_count = 0
    lock = threading.Lock()

    def worker():
        nonlocal allowed_count
        allowed, _ = m.consume("tuser")
        if allowed:
            with lock:
                allowed_count += 1

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert allowed_count == 10
    # 21st attempt still blocked
    assert m.consume("tuser")[0] is False


def test_manager_refund_logic_not_exceed_capacity():
    from code_indexer.server.auth.token_bucket import TokenBucketManager

    m = TokenBucketManager(capacity=3, refill_rate=1 / 6)
    # consume one, then refund should restore to capacity
    assert m.consume("refunduser")[0] is True
    tokens_after_consume = m.get_tokens("refunduser")
    assert 1.9 <= tokens_after_consume <= 3.0
    m.refund("refunduser")
    tokens_after_refund = m.get_tokens("refunduser")
    assert tokens_after_refund <= 3.0
    assert (
        tokens_after_refund >= 2.9
    )  # effectively back to capacity after refill rounding
