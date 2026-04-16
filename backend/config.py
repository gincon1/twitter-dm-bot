from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Feishu
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_app_token: str = ""
    feishu_table_targets: str = ""
    feishu_table_accounts: str = ""

    # AdsPower
    adspower_host: str = "http://local.adspower.net"
    adspower_port: int = 50325

    # Runtime limits
    daily_dm_limit: int = 5
    daily_dm_limit_min: int = 5
    daily_dm_limit_max: int = 5
    min_interval_sec: int = 900
    max_interval_sec: int = 2400
    sync_interval_min: int = 30
    reply_check_interval_min: int = 120
    reply_check_normal_interval_min: int = 120
    reply_check_start_hour: int = 10
    reply_check_end_hour: int = 2
    reply_check_full_interval_min: int = 360
    reply_check_full_start_hour: int = 10
    reply_check_full_end_hour: int = 2
    max_retry_accounts_per_target: int = 3
    followup_days: int = 3
    cooldown_hours: int = 12
    business_hours_start: int = 8
    business_hours_end: int = 23
    circuit_breaker_window_min: int = 30
    circuit_breaker_threshold: int = 3
    feishu_notify_webhook: str = ""

    # Web/API
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    cors_origins: str = "*"

    # Misc
    timezone: str = "Asia/Shanghai"
    runtime_db_path: str = "runtime.db"
    screenshot_dir: str = "artifacts/screenshots"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
