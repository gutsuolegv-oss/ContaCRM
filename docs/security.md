# Securitate: izolarea rețelei

Obiectiv: **serverul CRM nu are acces la internet**, cu o singură excepție controlată:
gateway-ul de notificări poate ajunge la Telegram și la serverul SMTP, doar prin proxy-ul cu listă albă.
Arhitectura generală este descrisă în [architecture.md](architecture.md).

## Trei niveluri de protecție

Fiecare nivel funcționează și singur. Împreună, o greșeală într-unul nu deschide accesul la internet.

| Nivel | Unde | Ce face |
|---|---|---|
| 1. Rețele Docker | `docker-compose.yml` | `crm_internal`, `gw_link` și `egress` sunt `internal: true`: Docker nu le dă rută spre exterior. Doar `egress-proxy` e în rețeaua `outbound`. |
| 2. Proxy cu listă albă | `infra/egress-proxy/squid.conf` | Acceptă doar tuneluri `CONNECT` de la gateway, doar spre `api.telegram.org:443` și serverul SMTP. Orice altă cerere e refuzată și jurnalizată. |
| 3. Firewall | host-ul VM-ului + firewall-ul de perimetru (router, pfSense, Proxmox) | Chiar dacă nivelurile 1–2 sunt ocolite, pachetele spre internet sunt aruncate. Doar IP-ul proxy-ului poate ieși, și doar spre IP-urile Telegram și ale serverului SMTP. |

## Nivelul 3: reguli de firewall pe host (Linux, iptables `DOCKER-USER`)

Docker gestionează singur regulile `iptables`. Regulile proprii se pun în lanțul `DOCKER-USER`,
care se evaluează înaintea celor generate de Docker.

Înlocuiește valorile dintre `< >`:

```bash
#!/bin/sh
# /usr/local/sbin/contacrm-firewall.sh — rulat la pornire, după Docker
LAN=<192.168.1.0/24>          # rețeaua biroului
DNS=<192.168.1.1>             # resolver-ul DNS intern
SMTP=<IP-ul serverului SMTP>
PROXY=172.30.0.10             # egress-proxy (adresă fixă din docker-compose.yml)

iptables -F DOCKER-USER
iptables -A DOCKER-USER -m conntrack --ctstate ESTABLISHED,RELATED -j RETURN

# Contabilii din birou → web (portul 443 publicat)
iptables -A DOCKER-USER -s $LAN -d 172.31.0.0/24 -p tcp --dport 443 -j RETURN

# Proxy → DNS intern (ca să rezolve api.telegram.org)
iptables -A DOCKER-USER -s $PROXY -d $DNS -p udp --dport 53 -j RETURN
iptables -A DOCKER-USER -s $PROXY -d $DNS -p tcp --dport 53 -j RETURN

# Proxy → Telegram (lista oficială: https://core.telegram.org/resources/cidr.txt)
for NET in 91.108.56.0/22 91.108.4.0/22 91.108.8.0/22 91.108.16.0/22 91.108.12.0/22 \
           149.154.160.0/20 91.105.192.0/23 91.108.20.0/22 185.76.151.0/24; do
  iptables -A DOCKER-USER -s $PROXY -d $NET -p tcp --dport 443 -j RETURN
done

# Proxy → SMTP
iptables -A DOCKER-USER -s $PROXY -d $SMTP -p tcp --dport 587 -j RETURN

# Tot restul traficului din containere: aruncat și jurnalizat
iptables -A DOCKER-USER -s 172.28.0.0/16 -j DROP
iptables -A DOCKER-USER -s 172.30.0.0/24 -j LOG --log-prefix "contacrm-egress-drop: " --log-level 4
iptables -A DOCKER-USER -s 172.30.0.0/24 -j DROP
iptables -A DOCKER-USER -s 172.31.0.0/24 -j DROP
iptables -A DOCKER-USER -j RETURN
```

Lista de IP-uri Telegram se poate schimba. Verific-o periodic la
<https://core.telegram.org/resources/cidr.txt>. Dacă vrei să eviți întreținerea listei, poți lăsa
proxy-ul să iasă pe 443 spre orice IP, iar filtrarea pe domeniu rămâne în seama nivelului 2.

**IPv6:** Docker nu activează IPv6 implicit. Păstrează-l dezactivat
(`"ipv6": false` în `/etc/docker/daemon.json`) sau aplică reguli echivalente cu `ip6tables`.

### Sistemul de operare al VM-ului

Și host-ul trebuie restricționat, nu doar containerele. Pe firewall-ul de perimetru, regula pentru VM:

| Sursă | Destinație | Port | Acțiune |
|---|---|---|---|
| VM CRM | IP-uri Telegram | 443/tcp | permis |
| VM CRM | server SMTP | 587/tcp | permis |
| VM CRM | mirror intern de pachete / registru Docker | 443/tcp | permis |
| VM CRM | NTP intern | 123/udp | permis |
| Rețeaua biroului | VM CRM | 443/tcp | permis |
| Admin (IP fix sau VPN) | VM CRM | 22/tcp | permis |
| VM CRM | orice altceva | * | **blocat** |

## Telegram fără porturi deschise

- Botul folosește **long polling** (`getUpdates`): gateway-ul întreabă Telegram dacă are mesaje noi.
  Toate conexiunile sunt inițiate din interior.
- **Nu** se folosește webhook: ar necesita ca serverul să fie accesibil public din internet.
- Tokenul botului stă **doar** în gateway (`TELEGRAM_BOT_TOKEN`). Backend-ul și worker-ul nu îl au.

## Protecție împotriva scurgerii datelor prin Telegram

Canalul spre Telegram e deschis, deci poate fi folosit abuziv dacă serverul CRM e compromis. Măsuri:

1. **Doar șabloane fixe.** Gateway-ul acceptă `template` + `params` validați (tip, lungime, format),
   nu text liber.
2. **Doar destinatari legați.** Mesajele pleacă doar către `chat_id`-uri care au pornit botul prin link-ul
   unic generat în CRM. Telegram oricum nu permite unui bot să scrie cuiva care nu l-a pornit.
3. **Limită de volum:** implicit 30 de mesaje pe minut (`GATEWAY_RATE_LIMIT_PER_MINUTE`). La depășire
   gateway-ul refuză cererile și alertează adminul.
4. **Jurnal de audit** în gateway: fiecare mesaj trimis sau primit, cu ora, șablonul și destinatarul.
5. **Gateway-ul nu poate ajunge la CRM:** rețeaua `gw_link` îl conține doar pe `worker`, care nu ascultă
   pe niciun port.
6. **Container minim:** gateway-ul rulează `read_only`, fără capabilități Linux (`cap_drop: ALL`),
   cu `no-new-privileges`.

## Actualizări și livrarea codului

Serverul CRM nu descarcă nimic din internet. Actualizările ajung astfel:

- **Imaginile aplicației** se construiesc pe o mașină de build sau în GitHub Actions, se publică într-un
  registru intern (ex. Harbor, Nexus, sau `docker save` / `docker load` pe un mediu de transfer), iar
  serverul le descarcă doar de acolo.
- **Pachetele sistemului de operare** vin dintr-un mirror intern (ex. `apt-cacher-ng`, Nexus) sau într-o
  fereastră de mentenanță planificată, în care regula de ieșire se deschide temporar.
- **Imaginile de bază** (`postgres`, `redis`, `squid`) se oglindesc în registrul intern.

## Verificare după instalare

Toate comenzile trebuie să se comporte exact așa. Orice abatere înseamnă o breșă în izolare.

```bash
# 1. Backend-ul NU are internet → trebuie să EȘUEZE
docker compose exec backend python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"

# 2. Worker-ul NU are internet → trebuie să EȘUEZE
docker compose exec worker python -c "import urllib.request; urllib.request.urlopen('https://api.telegram.org', timeout=5)"

# 3. Gateway-ul ajunge la Telegram prin proxy → trebuie să REUȘEASCĂ (răspuns 404 de la Telegram e OK)
docker compose exec notify-gateway python -c "import urllib.request; urllib.request.urlopen('https://api.telegram.org', timeout=5)"

# 4. Gateway-ul NU ajunge la alte site-uri → trebuie să EȘUEZE (403 de la proxy)
docker compose exec notify-gateway python -c "import urllib.request; urllib.request.urlopen('https://example.com', timeout=5)"

# 5. Jurnalul proxy-ului arată cererea refuzată de la pasul 4
docker compose logs egress-proxy | grep TCP_DENIED
```

## Alte reguli

- `.env` nu intră niciodată în git; în repository există doar `.env.example`.
- Secretele (`APP_SECRET_KEY`, `GATEWAY_API_KEY`, `TELEGRAM_BOT_TOKEN`, parolele) se generează
  aleatoriu, se schimbă la plecarea unui angajat cu acces și nu se trimit prin chat sau email.
- Datele despre datoriile clienților nu sunt trimise de backend către rolul Contabil (vezi RBAC), deci
  nu ajung nici în browser.

## Decizii luate: de implementat după funcționalul de bază

Stabilite în discuție, încă neimplementate:

1. **VM separată pentru gateway și proxy** (nu pe aceeași VM cu CRM-ul). Firewall-ul de perimetru
   blochează orice ieșire a VM-ului CRM; doar VM-ul gateway ajunge la Telegram și SMTP.
   De făcut: `docker-compose.yml` împărțit în două (CRM, respectiv `gateway/docker-compose.yml`).
2. **HTTPS în rețeaua locală cu o autoritate de certificare (CA) internă.** Certificatul serverului CRM
   include IP-ul (ex. `192.168.x.150`) și un nume (ex. `crm.birou.internal`). Certificatul CA-ului se
   instalează pe calculatoarele biroului.
3. **Acces la CRM în patru straturi:**
   1. `iptables` + `ipset`: doar IP-urile din listă (cu rezervări DHCP pe router);
   2. **certificat de client (mTLS) obligatoriu**: fiecare dispozitiv primește propriul `.p12`, cu cheie
      neexportabilă; nginx refuză conexiunile fără certificat valid; revocarea se face prin CRL;
   3. utilizator + parolă (2FA opțional);
   4. RBAC (Admin / Contabil).
4. **mTLS și între VM-ul CRM și VM-ul gateway**, cu certificate emise de același CA intern.
5. Scripturi de livrat: creare CA, emitere și revocare certificate `.p12`, reguli iptables/ipset,
   instrucțiuni de instalare a certificatului pe un calculator nou.
