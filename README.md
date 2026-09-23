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
