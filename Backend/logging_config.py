import os
import logging
import time
import traceback
from typing import Any
from supabase import create_client, Client

_supabase_client = None

def get_supabase() -> Client:
    global _supabase_client
    if _supabase_client is None:
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not supabase_url or not supabase_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables must be set")

        _supabase_client = create_client(supabase_url, supabase_key)

    return _supabase_client


class SupabaseLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        # Prevent infinite loop: Don't log messages from Supabase client itself
        if record.name.startswith('supabase') or record.name.startswith('httpx') or record.name.startswith('httpcore'):
            return

        try:
            log_entry = self.format_log_entry(record)

            # Insert into Supabase (fail-silent if network/DB issue)
            supabase = get_supabase()
            supabase.table("system_logs").insert(log_entry).execute()

        except Exception as e:
            print(f"[LOGGING ERROR] Failed to write log to Supabase: {e}")
            print(f"[LOGGING ERROR] Original log: {record.getMessage()}")

    def format_log_entry(self, record: logging.LogRecord) -> dict:
        extra = getattr(record, "extra_fields", {})

        log_entry = {
            "level": record.levelname,
            "category": extra.get("category", "system"),
            "action": extra.get("action", record.funcName),
            "user_id": extra.get("user_id"),
            "user_email": extra.get("user_email"),
            "endpoint": extra.get("endpoint"),
            "http_method": extra.get("http_method"),
            "status_code": extra.get("status_code"),
            "duration_ms": extra.get("duration_ms"),
            "metadata": extra.get("metadata", {}),
            "error_message": record.getMessage() if record.levelno >= logging.ERROR else None,
        }

        # Add stack trace for errors
        if record.exc_info:
            log_entry["metadata"]["stack_trace"] = "".join(
                traceback.format_exception(*record.exc_info)
            )

        return log_entry


def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)  # Capture INFO and above

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    supabase_handler = SupabaseLogHandler()
    supabase_handler.setLevel(logging.INFO)  # Don't log DEBUG to database
    root_logger.addHandler(supabase_handler)

    # Suppress noisy third-party library logs
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("supabase").setLevel(logging.WARNING)

    return root_logger


def log_api_request(
    logger: logging.Logger,
    user_id: str | None,
    user_email: str | None,
    endpoint: str,
    http_method: str,
    status_code: int,
    duration_ms: int,
    category: str = "api_request",
    action: str = None,
    metadata: dict = None,
):

    extra_fields = {
        "category": category,
        "action": action or endpoint.split("/")[-1],
        "user_id": user_id,
        "user_email": user_email,
        "endpoint": endpoint,
        "http_method": http_method,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "metadata": metadata or {},
    }

    log_record = logger.makeRecord(
        logger.name,
        logging.INFO,
        "(logging_config)",
        0,
        f"{http_method} {endpoint} -> {status_code} ({duration_ms}ms)",
        (),
        None,
    )
    log_record.extra_fields = extra_fields

    logger.handle(log_record)
