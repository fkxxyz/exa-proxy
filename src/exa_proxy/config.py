from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UpstreamConfig(BaseModel):
    name: str
    url: str
    authorization: str | None = None
    enabled: bool = True
    cooldown_seconds: int = 60


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="EXA_PROXY_", extra="ignore")

    host: str = "127.0.0.1"
    port: int = 8080
    log_payloads: bool = True
    upstreams: list[UpstreamConfig] = Field(default_factory=list)
