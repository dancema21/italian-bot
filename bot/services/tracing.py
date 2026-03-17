"""
Phoenix Cloud OTEL tracing — fully optional.
If PHOENIX_API_KEY or PHOENIX_COLLECTOR_ENDPOINT are not set, a no-op tracer
is returned everywhere and the bot runs normally without any tracing overhead.
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_tracer = None


class _NoopSpan:
    """Drop-in span used when tracing is disabled — zero overhead."""
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def set_attribute(self, key, value):
        pass


class _NoopTracer:
    def start_as_current_span(self, name, **kwargs):
        return _NoopSpan()


_NOOP = _NoopTracer()


def _initialize():
    global _tracer
    api_key = os.environ.get("PHOENIX_API_KEY")
    endpoint = os.environ.get("PHOENIX_COLLECTOR_ENDPOINT")
    project_name = os.environ.get("PHOENIX_PROJECT_NAME", "italian-bot")

    if not api_key or not endpoint:
        logger.info("Phoenix tracing disabled (env vars not set)")
        return

    try:
        from phoenix.otel import register
        register(
            project_name=project_name,
            endpoint=endpoint,
            api_key=api_key,
        )
        from opentelemetry.instrumentation.google_genai import GoogleGenAiSdkInstrumentor
        GoogleGenAiSdkInstrumentor().instrument()
        from opentelemetry import trace
        _tracer = trace.get_tracer("italian-bot")
        logger.info(f"Phoenix tracing enabled — project: {project_name}")
    except Exception as e:
        logger.warning(f"Phoenix tracing setup failed (non-critical): {e}")


def get_tracer() -> _NoopTracer:
    """Return the active OTel tracer, or a no-op tracer if tracing is disabled."""
    return _tracer if _tracer is not None else _NOOP


# Initialize at import time so auto-instrumentation is active before any
# Gemini client is created. main.py imports this module after load_dotenv().
_initialize()
