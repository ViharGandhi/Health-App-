"""Request-local timing counters; no tokens, identifiers or health values."""
from contextvars import ContextVar

read_metrics = ContextVar('read_metrics', default=None)


def count(name: str, value: float = 1):
    metrics = read_metrics.get()
    if metrics is not None:
        metrics[name] = metrics.get(name, 0) + value
