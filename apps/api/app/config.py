from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../../.env", ".env"), extra="ignore")

    deepseek_api_key: SecretStr | None = None
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    admin_api_key: SecretStr | None = None
    database_url: str = "postgresql+psycopg://dd_cafe:dd_cafe_local@localhost:5432/dd_cafe"
    redis_url: str = "redis://localhost:6379/0"
    redis_checkpoints: bool = True
    checkpoint_ttl_minutes: int = 120
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "dd_cafe_knowledge"
    rag_dense_model: str = "BAAI/bge-small-zh-v1.5"
    rag_reranker_model: str = "BAAI/bge-reranker-base"
    rag_reranker_enabled: bool = True
    rag_reranker_prewarm: bool = True
    web_search_enabled: bool = True
    auto_create_schema: bool = True
    seed_demo_data: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    vision_api_key: SecretStr | None = None
    vision_model: str = "qwen3-vl-flash"
    vision_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    max_upload_size_mb: int = 10
    upload_dir: str = "data/uploads"
    image_gen_model: str = "qwen-image-max"
    image_gen_size: str = "1328*1328"
    image_edit_model: str = "qwen-image-edit"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
