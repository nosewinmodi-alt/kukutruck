from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    environment: str = "development"
    database_url: str = "sqlite:///./kukutrack.db"
    secret_key: str = "change-me"
    access_token_minutes: int = 60 * 24 * 7
    cors_origins: str = "*"
    trial_days: int = 30
    upload_dir: str = "./uploads"
    plan_price_kes: int = 500
    # Shared secret embedded in webhook URLs (M-Pesa callback, USSD)
    callback_secret: str = "change-me-too"
    public_base_url: str = "https://example.com"
    # Africa's Talking (SMS + USSD)
    at_username: str = "sandbox"
    at_api_key: str = ""
    at_sender: str = ""
    # Safaricom Daraja
    mpesa_env: str = "sandbox"
    mpesa_consumer_key: str = ""
    mpesa_consumer_secret: str = ""
    mpesa_shortcode: str = "174379"
    mpesa_passkey: str = ""


settings = Settings()
