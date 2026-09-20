# Backend package
# Load backend/.env before any submodule reads env vars (KAFKA_BOOTSTRAP,
# DATABASE_URL, API keys). No-op in containers: .env is dockerignored and
# existing environment is never overridden.
from dotenv import load_dotenv

load_dotenv()
