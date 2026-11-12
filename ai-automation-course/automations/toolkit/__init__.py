"""The shared code every automation uses. Each file is one idea."""
from dotenv import load_dotenv

# On your laptop the settings come from .env. On Cloud Run there is no .env:
# deploy.sh passes the settings in, and the secrets come from Secret Manager.
load_dotenv()
