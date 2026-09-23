# ContaCRM

CRM pentru firme de contabilitate din Moldova.

## Funcționalități
- Clasificarea rapoartelor (plătitori TVA → R1, R2, R3 | non-plătitori → R4, R5, R6)
- Cartele client (date legale, conturi bancare, contacte)
- Transport tracking cu notificări
- Distribuția clienților pe contabili (RBAC: Admin, Contabil)
- Notificări email + Telegram
- Onboarding wizard
- Sync 1C → detecția restanțelor

## Stack
- **Backend:** FastAPI (Python 3.11+)
- **Database:** PostgreSQL 15+
- **Frontend:** React + TypeScript
- **Cache / Queue:** Redis, Celery
- **Realtime:** WebSocket (FastAPI)
- **Notificări:** SMTP + Telegram Bot

## Demo design (mockup)
Prototip vizual interactiv, fără backend, cu date fictive: [`mockup/index.html`](mockup/index.html).
Se deschide direct în browser (dublu-click) sau:
```bash
python -m http.server 5500 --directory mockup
```
apoi http://localhost:5500
