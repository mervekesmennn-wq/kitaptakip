# Kitap Takip

Kitap okuma ilerlemesini ve yıllık hedefi takip eden Flask uygulaması.

## Kurulum

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
python application.py
```

Docker ile çalıştırma:

```bash
docker compose up -d --build
```

Uygulama: http://localhost:5010

Giriş: `test` / `123`