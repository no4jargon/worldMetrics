from __future__ import annotations


def emit_trace(trace_messages: list[str] | None, dataset_code: str, message: str) -> None:
    if trace_messages is None:
        return
    trace_messages.append(f'{dataset_code}: {message}')
