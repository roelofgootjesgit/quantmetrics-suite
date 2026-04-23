Goed. Dan zou ik **niet** eerst Sprint C bouwen.

Eerst deployen.
Eerst gebruiken.
Eerst voelen waar de echte pijn nog zit.

## Strategische analyse

De juiste volgorde is nu:

1. Ops Console op VPS zetten
2. browsermatig gebruiken op echte logs
3. 2–3 dagen observeren
4. daarna pas doorbouwen

Dat is de professionele volgorde.

Want nu moet je niet meer raden of de console werkt.
Je moet hem in je echte workflow drukken.

## Architectuurbeslissing

Voor nu zou ik gaan voor de simpelste, veilige deploy:

* Streamlit app
* aparte venv
* systemd service
* reverse proxy via Nginx
* optioneel basic auth of IP restriction
* read-only toegang tot je logmap

**Niet** meteen Docker.
**Niet** meteen database.
**Niet** meteen auth-complexiteit.

Gewoon: stabiel online krijgen.

---

## Virtualenv: waarom los van QuantBuild?

Op de VPS geldt in QuantBuild **`docs/VPS_MULTI_MODULE_DEPLOYMENT.md`** (§2–4): **één bot-virtualenv** onder `quantbuildv1/.venv` voor live run, QuantBridge-laden en (optioneel) `pip install -e` voor QuantLog CLI — bewust geen tweede “runtime”-venv voor spine-code.

De **Ops Console** is daar een **uitzondering** (staat ook in QuantBuild **§4.1**):

| Keuze | Motief |
|--------|--------|
| **Eigen `.venv` in `quantlogv1`** | Streamlit en gerelateerde UI-deps (`[project.optional-dependencies] ops`) staan **niet** in QuantBuild `requirements.txt`. Die in de bot-venv mixen vergroot kans op versie-conflict en maakt elke `pip install -r requirements.txt` onvoorspelbaarder. |
| **Niet de bot-venv voor systemd** | Upgrades van de console raken de live trading-process **niet**. Het Python-contract blijft **3.10.x** — gebruik dezelfde minor als je bot bij het aanmaken van deze venv. |
| **Zelfde repo** | `quantlog_ops` zit in **dezelfde** git-repo als `src/quantlog`; alleen de **interpreter-pad** voor de Streamlit-service is apart. |

Lokaal op een werkstation mag je alles in één venv houden voor gemak; **op de VPS** is deze splitsing de nette default.

---

# VPS Deploy Handboek — QuantLog Ops Console v0.1

Gebruik dit als praktische checklist.

## 1. Doel

De QuantLog Ops Console moet op je VPS draaien als een aparte read-only webapp, zodat jij:

* in browser je logs kunt bekijken
* niet meer hoeft te SSH’en om dagelijks logs op te halen
* dezelfde quantlog_events map kunt uitlezen als je trading stack gebruikt

---

## 2. Aanbevolen setup

Ik zou deze structuur gebruiken:

```bash
/opt/quantlogv1
/opt/quantlogv1/.venv
/opt/quantlogv1/quantlog_ops
/opt/quantlogv1/src
/opt/quantlogv1/docs
/var/log/quantlog_ops
```

En je event root bijvoorbeeld:

```bash
/opt/quantbuildv1/data/quantlog_events
```

Of waar jouw echte `YYYY-MM-DD/` mappen al staan.

---

## 3. Eerste check op de VPS

Log in en check eerst dit:

```bash
pwd
python3 --version
which python3
ls /opt
```

Controleer ook of je logmap echt bestaat:

```bash
ls /opt/quantbuildv1/data/quantlog_events
```

Je moet daar datumfolders zien.

---

## 4. Repo op de VPS

Als de repo al op de VPS staat:

```bash
cd /opt/quantlogv1
git pull
```

Als hij er nog niet staat:

```bash
cd /opt
git clone <jouw-repo-url> quantlogv1
cd quantlogv1
```

---

## 5. Python venv maken

**Repo-root:** kan `/opt/quantlogv1` zijn of bijv. `/root/quant_suite/quantlogv1` — het gaat om de map waar `pyproject.toml` en `quantlog_ops/` na `git pull` staan. Hieronder: `QUANTLOG_REPO` vervangen door jouw pad.

```bash
cd /path/to/quantlogv1    # jouw clone
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[ops]"
```

`pip install -e ".[ops]"` installeert de package editable **met** Streamlit/pandas; dat is voldoende voor de console (read-only op JSONL). Gebruik bij voorkeur **dezelfde Python 3.10.x** als je QuantBuild-bot op deze VPS (`docs/VPS_MULTI_MODULE_DEPLOYMENT.md` §2).

**Herinnering:** systemd voor deze app gebruikt **`…/quantlogv1/.venv/bin/python`**, niet `quantbuildv1/.venv` — zie §4.1 in QuantBuild `VPS_MULTI_MODULE_DEPLOYMENT.md`.

---

## 6. Environment variabelen

Voor de Ops Console zijn minimaal relevant:

```bash
QUANTLOG_OPS_EVENTS_ROOT=/opt/quantbuildv1/data/quantlog_events
QUANTLOG_OPS_TABLE_MAX_EVENTS=10000
QUANTLOG_OPS_HEALTH_MAX_EVENTS=20000
QUANTLOG_OPS_EXPLAINER_MAX_EVENTS=20000
```

Test eerst handmatig:

```bash
export QUANTLOG_OPS_EVENTS_ROOT=/opt/quantbuildv1/data/quantlog_events
export QUANTLOG_OPS_TABLE_MAX_EVENTS=10000
export QUANTLOG_OPS_HEALTH_MAX_EVENTS=20000
export QUANTLOG_OPS_EXPLAINER_MAX_EVENTS=20000
```

---

## 7. Handmatig starten

Eerst lokaal op de VPS testen zonder systemd:

```bash
cd /opt/quantlogv1
source .venv/bin/activate
python -m streamlit run quantlog_ops/app.py --server.port 8501 --server.address 127.0.0.1
```

Als dit goed start, zie je in output dat Streamlit luistert op localhost.

Controleer dan op de VPS zelf:

```bash
curl http://127.0.0.1:8501
```

Als je HTML terugkrijgt, draait hij.

---

## 8. systemd service maken

Maak bestand:

```bash
sudo nano /etc/systemd/system/quantlog-ops.service
```

Inhoud:

```ini
[Unit]
Description=QuantLog Ops Console
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/quantlogv1
Environment=QUANTLOG_OPS_EVENTS_ROOT=/opt/quantbuildv1/data/quantlog_events
Environment=QUANTLOG_OPS_TABLE_MAX_EVENTS=10000
Environment=QUANTLOG_OPS_HEALTH_MAX_EVENTS=20000
Environment=QUANTLOG_OPS_EXPLAINER_MAX_EVENTS=20000
ExecStart=/opt/quantlogv1/.venv/bin/python -m streamlit run quantlog_ops/app.py --server.port 8501 --server.address 127.0.0.1
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Dan:

```bash
sudo systemctl daemon-reload
sudo systemctl enable quantlog-ops
sudo systemctl start quantlog-ops
sudo systemctl status quantlog-ops
```

---

## 9. Logs bekijken

Als er iets misgaat:

```bash
journalctl -u quantlog-ops -n 100 --no-pager
```

Live meekijken:

```bash
journalctl -u quantlog-ops -f
```

Dit is je eerste debugpunt als deploy niet opkomt.

---

## 10. Nginx reverse proxy

Installeer Nginx als die nog niet draait:

```bash
sudo apt update
sudo apt install nginx -y
```

Maak config:

```bash
sudo nano /etc/nginx/sites-available/quantlog-ops
```

Inhoud:

```nginx
server {
    listen 80;
    server_name jouw-domein-of-vps-ip;

    location / {
        proxy_pass http://127.0.0.1:8501/;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

Dan:

```bash
sudo ln -s /etc/nginx/sites-available/quantlog-ops /etc/nginx/sites-enabled/quantlog-ops
sudo nginx -t
sudo systemctl reload nginx
```

Dan kun je via browser naar je VPS-IP of domein.

---

## 11. Minimale beveiliging

Voor nu zou ik minstens één van deze twee doen:

### Optie A — alleen jouw IP toelaten in Nginx

In de `location /`:

```nginx
allow JOUW.IP.ADRES.HIER;
deny all;
```

### Optie B — basic auth

Dat is ook prima, maar IP restriction is voor nu vaak sneller.

Voor een interne ops console is dat genoeg als eerste stap.

---

## 12. Firewall

Als UFW actief is:

```bash
sudo ufw allow 'Nginx Full'
sudo ufw status
```

Je hoeft poort 8501 niet extern open te zetten als Nginx proxyt op localhost.

Dat is beter.

---

## 13. Deployment checklijst

Als alles goed staat, moet dit werken:

* `systemctl status quantlog-ops` = active
* `curl 127.0.0.1:8501` geeft HTML
* `nginx -t` is ok
* browser opent de console
* datumfolders worden geladen
* run-overzicht werkt
* no-trade explainer werkt
* downloads werken

---

## 14. Meest waarschijnlijke fouten

### 1. Verkeerde events root

Symptoom: app opent, maar geen dagen/runs zichtbaar.

Check:

```bash
ls /opt/quantbuildv1/data/quantlog_events
```

### 2. Editable install of importpad fout

Symptoom: service crasht direct.

Check:

```bash
journalctl -u quantlog-ops -n 100 --no-pager
```

### 3. Streamlit draait, Nginx niet goed

Symptoom: localhost werkt, browser extern niet.

Check:

```bash
curl http://127.0.0.1:8501
sudo nginx -t
sudo systemctl status nginx
```

### 4. Rechtenprobleem op logmap

Symptoom: app draait, maar kan geen files lezen.

Check:

```bash
ls -lah /opt/quantbuildv1/data/quantlog_events
```

---

## 15. Mijn advies voor jouw setup

Ik zou dit exact zo doen:

* Streamlit alleen op `127.0.0.1:8501`
* Nginx ervoor
* IP restriction aan
* systemd restart always
* event root hard zetten in service file
* eerst draaien op demo/live logs zonder extra features

Dat is de kortste route naar een bruikbare deploy.

---

## 16. Slimme volgorde voor jou vandaag

Doe dit in deze volgorde:

1. handmatig starten op VPS
2. check of hij de juiste logdagen ziet
3. systemd service maken
4. Nginx proxy ervoor
5. browser openen
6. 1 echte dag reviewen

Dat is de snelste manier om echte feedback te krijgen.

Als je wilt, maak ik hier direct een **copy-paste VPS deploy MD** van met de exacte commands en bestandsinhoud, zodat je die één op één in Cursor of op de server kunt gebruiken.
