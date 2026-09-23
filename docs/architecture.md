# Arhitectura ContaCRM

## Principiu de bază

**Serverul CRM nu are acces la internet.** Toate datele (clienți, conturi bancare, rapoarte,
datorii din 1C) rămân în rețeaua internă. Singura componentă care comunică cu exteriorul este
**gateway-ul de notificări**. El poate ajunge doar la `api.telegram.org` și la serverul SMTP,
și doar printr-un proxy de ieșire cu listă albă.

```
          Rețeaua biroului / VPN (contabilii, adminul)
                         │ HTTPS 443
                         ▼
┌──────────────────────── ZONA CRM (fără internet) ────────────────────────┐
│                                                                          │
│   web (nginx) ──► backend (FastAPI + WebSocket) ──► PostgreSQL           │
│                          │                     └──► Redis                │
│                          ▼                                               │
│                 worker (Celery) ◄── beat (planificator)                  │
│                          │                                               │
│                          │ ◄── sync 1C (rețea internă)                   │
└──────────────────────────┼───────────────────────────────────────────────┘
                           │ HTTP intern, doar worker → gateway
                           │ (cheie API; gateway-ul NU poate iniția conexiuni spre CRM)
┌──────────────────────────┼─────── ZONA GATEWAY ──────────────────────────┐
│                          ▼                                               │
│               notify-gateway (deține tokenul botului)                    │
│                          │                                               │
│                          ▼                                               │
│               egress-proxy (Squid, listă albă)                           │
└──────────────────────────┼───────────────────────────────────────────────┘
                           │ doar CONNECT spre:
                           ▼   api.telegram.org:443, smtp.<furnizor>:587
                       INTERNET
```

## Componente

| Serviciu | Rol | Rețele Docker | Internet |
|---|---|---|---|
| `web` | nginx: servește frontend-ul React, proxy spre backend, TLS | `web_public`, `crm_internal` | ❌ (blocat pe host) |
| `backend` | FastAPI: API REST, WebSocket, RBAC | `crm_internal` | ❌ |
| `worker` | Celery: notificări, generare foi de parcurs, sync 1C | `crm_internal`, `gw_link` | ❌ |
| `beat` | Celery beat: sarcini programate (ex. verificare kilometraj în ultima zi a lunii) | `crm_internal` | ❌ |
| `postgres` | Baza de date | `crm_internal` | ❌ |
| `redis` | Cache + broker Celery | `crm_internal` | ❌ |
| `notify-gateway` | Telegram Bot (long polling) + trimitere email | `gw_link`, `egress` | doar prin proxy |
| `egress-proxy` | Squid: permite doar domeniile din listă albă | `egress`, `outbound` | ✅ doar Telegram + SMTP |

## De ce un gateway separat

1. **Tokenul botului nu există pe serverul CRM.** Dacă serverul CRM e compromis, atacatorul nu poate
   folosi botul direct.
2. **CRM-ul nu poate trimite text arbitrar.** Worker-ul trimite doar *comenzi* de forma
   `{"template": "km_request", "params": {...}}`. Gateway-ul construiește mesajul dintr-un șablon fix
   și validează fiecare parametru. Așa nu se poate scurge baza de date prin Telegram.
3. **Direcția conexiunilor e unică.** Worker-ul întreabă gateway-ul, iar gateway-ul nu are nicio cale
   spre backend, baza de date sau Redis. Singurul lui vecin în rețeaua `gw_link` este worker-ul, care
   nu ascultă pe niciun port.
4. **Limitare și audit.** Gateway-ul limitează numărul de mesaje pe minut și păstrează un jurnal
   propriu al fiecărui mesaj trimis sau primit.
5. **Fără porturi deschise din internet.** Telegram e folosit prin *long polling* (`getUpdates`), nu
   prin webhook.

## Contractul worker ↔ gateway

Autentificare: antetul `Authorization: Bearer <GATEWAY_API_KEY>`. Toate apelurile sunt inițiate de worker.

### `POST /v1/messages`: trimite o notificare

```json
{
  "id": "5f0c…",
  "channel": "telegram",
  "chat_id": 123456789,
  "template": "km_request",
  "params": { "plate": "CHL 218", "model": "Renault Kangoo", "month": "2026-08", "last_odometer": 122266 }
}
```

- `id` este generat de CRM și face cererea idempotentă: o comandă repetată nu duce la un mesaj dublu.
- Gateway-ul respinge (`422`) orice șablon necunoscut sau parametru care nu trece validarea
  (ex. `plate` trebuie să fie de forma `ABC 123`, `month` de forma `AAAA-LL`, numerele trebuie să fie întregi pozitive).
- Pentru email: `"channel": "email"`, `"to": "…"`, același mecanism de șabloane.

### `GET /v1/inbox?after=<cursor>`: evenimente primite

Worker-ul interoghează periodic (ex. la fiecare 10 s). Răspuns:

```json
{
  "cursor": "1042",
  "events": [
    { "type": "km_reading", "request_id": "5f0c…", "chat_id": 123456789, "value": 123906, "received_at": "2026-09-03T10:12:00+03:00" },
    { "type": "link", "code": "K7Q2-9XPA", "chat_id": 987654321, "received_at": "…" }
  ]
}
```

- `km_reading`: clientul a răspuns cu odometrul. Gateway-ul extrage doar numărul și trimite
  `request_id`-ul cererii la care s-a răspuns. Textul brut nu ajunge în CRM.
- `link`: un contact al clientului a pornit botul printr-un link unic
  (`t.me/ContaCRM_bot?start=K7Q2-9XPA`) generat în cartela clientului. CRM-ul leagă codul de contact
  și salvează `chat_id`.

### Șabloane inițiale

| Șablon | Când | Parametri |
|---|---|---|
| `km_request` | ultima zi a lunii, 18:00, dacă lipsesc datele | `plate`, `model`, `month`, `last_odometer` |
| `km_reminder` | la 3 zile după, dacă tot lipsesc | `plate`, `month` |
| `km_ack` | după primirea odometrului | `plate`, `value`, `km_driven` |
| `report_deadline` | cu 3 zile înainte de termen (către contabil) | `report`, `period`, `count` |
| `link_welcome` | după legarea contului | `client_name` |

## Fluxul Parc auto (exemplu complet)

1. `beat` pornește în ultima zi a lunii la 18:00 sarcina `check_missing_odometer`.
2. `worker` găsește automobilele fără date și pentru fiecare face `POST /v1/messages` cu `km_request`.
3. `notify-gateway` trimite mesajul prin `egress-proxy` → `api.telegram.org`.
4. Clientul răspunde `123906`. Gateway-ul îl primește prin long polling, validează numărul și îl pune în inbox.
5. `worker` citește `GET /v1/inbox`, salvează odometrul și marchează automobilul „Date primite”.
   Contabilul vede asta în timp real (WebSocket).
6. Contabilul generează foaia de parcurs, iar `worker` trimite `km_ack`.

## Actualizări și livrarea codului

Serverul CRM nu poate face `git pull` sau `pip install` din internet. Codul ajunge astfel:
imaginile Docker se construiesc pe o mașină de build (sau în GitHub Actions), se publică într-un
registru intern, iar serverul CRM le descarcă doar din acel registru. Detalii în [security.md](security.md).
