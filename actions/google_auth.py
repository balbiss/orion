import sys
import subprocess
import webbrowser
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

CREDENTIALS_PATH = _base_dir() / "config" / "credentials.json"
TOKEN_PATH       = _base_dir() / "config" / "google_token.json"

_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _open_in_chrome(url: str) -> bool:
    for path in _CHROME_PATHS:
        if Path(path).exists():
            subprocess.Popen([path, url])
            return True
    # fallback: try via shell
    try:
        subprocess.Popen(f'start chrome "{url}"', shell=True)
        return True
    except Exception:
        return False


def get_google_creds() -> Credentials:
    creds = None

    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("[Google Auth] Abrindo Chrome para autorizar o ORION...")
            print("[Google Auth] AGUARDE: faca login no Google e clique em 'Permitir'.")
            print("[Google Auth] NAO feche o ORION enquanto authoriza!")

            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)

            # Force Chrome to open instead of the default browser
            _orig_open = webbrowser.open
            webbrowser.open = lambda url, new=0, autoraise=True: _open_in_chrome(url) or _orig_open(url, new, autoraise)

            try:
                creds = flow.run_local_server(
                    port=8085,
                    success_message="Autorizado! Pode fechar esta aba e voltar ao ORION.",
                    timeout_seconds=120,
                )
            except Exception as e:
                webbrowser.open = _orig_open
                print(f"[Google Auth] Falha na autorizacao: {e}")
                raise RuntimeError(
                    "Autorizacao Google nao concluida. Abra o Chrome, faca login e clique em Permitir. "
                    "Se aparecer 'Acesso bloqueado', veja as instrucoes de configuracao."
                ) from e
            finally:
                webbrowser.open = _orig_open

            print("[Google Auth] Autorizacao concluida! Token salvo.")
        TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")

    return creds
