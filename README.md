# ContaCRM

CRM pentru firme de contabilitate din Moldova.

## Funcționalități
- Clasificarea rapoartelor (plătitori TVA → R1, R2, R3 | non-plătitori → R4, R5, R6)
- Cartele client (date legale, conturi bancare, contacte)
- Parc auto în cartela fiecărui client: evidența automobilelor, colectarea lunară a datelor la odometru (reamintire pe Telegram dacă lipsesc la sfârșitul lunii) și generarea foilor de parcurs
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

## Arhitectură și securitate
Serverul CRM rulează **fără acces la internet**. Singura ieșire este gateway-ul de notificări,
care ajunge doar la Telegram și la serverul SMTP, printr-un proxy cu listă albă.
- [docs/architecture.md](docs/architecture.md): componente, rețele, contractul worker ↔ gateway
- [docs/security.md](docs/security.md): reguli de firewall, protecție anti-scurgere, verificare
- [docker-compose.yml](docker-compose.yml): topologia serviciilor și rețelelor izolate

## Dezvoltare: pornire rapidă

Pe VM (Docker; Node nu e necesar pe host):

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend alembic upgrade head
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend python -m app.seed.demo
```

`app.seed.demo` încarcă clasificatorul, utilizatorii și clienții din mockup și grilele pe
august–septembrie 2026. Refuză să ruleze în producție. Parola tuturor utilizatorilor demo:
`demo-parola-2026`; logarea se face cu numele de utilizator (ex. `admin`, `ana.rusu`).

Aplicația și API-ul ascultă doar pe `127.0.0.1` al VM-ului. De pe calculatorul tău:

```bash
ssh -L 5173:127.0.0.1:5173 -L 8000:127.0.0.1:8000 wcontacrm@<ip-vm>
```

apoi <http://localhost:5173> (aplicația) și <http://localhost:8000/docs> (API).

Verificări:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec backend sh -c "ruff check . && mypy app tests migrations && pytest -q"
docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps frontend sh -c "npm run typecheck && npm run lint && npm test"
```

După o schimbare de API, tipurile din frontend se regenerează cu
`docker compose -f docker-compose.yml -f docker-compose.dev.yml run --rm --no-deps frontend npm run api-types`.

## Demo design (mockup)
Prototip vizual interactiv, fără backend, cu date fictive: [`mockup/index.html`](mockup/index.html).
Se deschide direct în browser (dublu-click) sau:
```bash
python -m http.server 5500 --directory mockup
```
apoi http://localhost:5500
