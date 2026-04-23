# VPS + SSH-key + VS Code Remote (start checklist)

Korte checklist voor **nieuwe projecten** of een **nieuwe VPS**: code op de server zetten/bijwerken en vanaf Windows **zonder wachtwoord** met VS Code op de Linux-map werken.

Uitgebreide deploy (systemd, secrets, QuantBridge): zie **`VPS_DEPLOYMENT_RUNBOOK.md`**. Waar alle credentials thuishoren (OS env): **`docs/CREDENTIALS_AND_ENVIRONMENT.md`**. Dagelijkse updates: **`OPERATOR_CHEATSHEET.md`**.

---

## 1) Aanbevolen layout op de VPS

```text
/opt/quantbuild/quantbuild    # deze repo
/opt/quantbuild/quantbridge      # QuantBridge (indien van toepassing)
/opt/quantbuild/quantlog_v1            # QuantLog (indien van toepassing; naam kan afwijken)
```

Controleren:

```bash
ls -la /opt/quantbuild/
```

---

## 2) Eerste update op de server (na clone of nieuwe machine)

```bash
cd /opt/quantbuild/quantbuild
source .venv/bin/activate
git fetch origin
git checkout v2-development   # of de branch die je gebruikt
git pull --ff-only
pip install -r requirements.txt
```

**Let op:** voer commando’s **apart** uit (Enter tussen regels). Niet plakken als `requirements.txtsudo ...` of `tail ...pip ...` op één regel.

Systemd-service herstarten na code-/dependency-update:

```bash
sudo systemctl restart quantbuild-ctrader-demo.service
sudo systemctl is-active quantbuild-ctrader-demo.service
```

---

## 3) Windows: VS Code + Remote SSH

1. Installeer **Visual Studio Code** (lokaal; op de VPS hoef je geen desktop-VS Code te installeren).
2. Extensie **Remote - SSH** (Microsoft).
3. Verbinden: **F1** → `Remote-SSH: Connect to Host...` → gebruik een **host-alias** uit je SSH-config (stap 4), niet blind je Windows-gebruikersnaam als SSH-user.

---

## 4) SSH-config op Windows (`%USERPROFILE%\.ssh\config`)

Vervang `JOUW_IP` en paden waar nodig. Gebruik **`root`** (of de user die op de VPS echt bestaat).

```sshconfig
Host quantbuild-vps
    HostName JOUW_IP
    User root
    IdentityFile C:/Users/JOUW_WINDOWS_USER/.ssh/id_ed25519_quantbuild_vps
    IdentitiesOnly yes

Host JOUW_IP
    User root
    IdentityFile C:/Users/JOUW_WINDOWS_USER/.ssh/id_ed25519_quantbuild_vps
    IdentitiesOnly yes
```

**Waarom dit zo staat**

- **`IdentityFile`** met **volledig pad** (`C:/Users/...`): sommige VS Code / OpenSSH-combinaties expanderen `~` anders dan in de terminal.
- **`IdentitiesOnly yes`**: voorkomt te veel key-pogingen; anders kan de server op **wachtwoord** overschakelen terwijl je key wél goed is.
- **`Host JOUW_IP`**: dezelfde key als je in VS Code **`root@IP`** kiest i.p.v. de alias.

---

## 5) SSH-key aanmaken (eenmalig per PC)

PowerShell:

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\id_ed25519_quantbuild_vps" -q -N '""' -C "quantbuild-vps"
```

Public key tonen (alleen deze **enkele regel** hoort op de server):

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_quantbuild_vps.pub"
```

---

## 6) Public key op de VPS (`authorized_keys`)

**Op de VPS** (PuTTY of remote terminal):

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys
```

Plak **exact de ene regel** die begint met `ssh-ed25519 AAAA...`.  
**Niet** plakken: PowerShell-commando’s zoals `Get-Content ...` — dat is geen geldige key.

Opslaan in nano: **Ctrl+O**, Enter, **Ctrl+X**. Daarna:

```bash
chmod 600 ~/.ssh/authorized_keys
```

**Alternatief (één keer wachtwoord vanaf Windows):**

```powershell
Get-Content "$env:USERPROFILE\.ssh\id_ed25519_quantbuild_vps.pub" | ssh root@JOUW_IP "mkdir -p ~/.ssh && chmod 700 ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
```

Test zonder wachtwoord:

```powershell
ssh quantbuild-vps
```

---

## 7) VS Code: projectmap openen en bewaren

1. Verbonden met Remote SSH → **File → Open Folder** → `/opt/quantbuild/quantbuild` (volledige pad in het padveld plakken mag).
2. **File → Save Workspace As...** op Windows (bijv. `vscode-workspaces/quantbuild-vps.code-workspace`) voor snel opnieuw openen.
3. Python: interpreter kiezen op `.venv/bin/python` in die repo (extensie Python op “SSH” installeren indien gevraagd).

---

## 8) VS Code vraagt wél om wachtwoord (terwijl `ssh` in PowerShell werkt)

1. Verbind met **`quantbuild-vps`**, niet alleen per ongeluk een andere user/host-combo.
2. Controleer **Remote-SSH: Show Log**.
3. Settings: **`remote.SSH.configFile`** moet leeg zijn of naar jouw echte `C:\Users\...\`.ssh\config` wijzen.
4. Houd **`IdentitiesOnly yes`** en het **volledige pad** naar `IdentityFile` in de config (stap 4).

---

## 9) Beveiliging (kort)

- De **private key** (`id_ed25519_quantbuild_vps` zonder `.pub`) nooit delen of in git zetten.
- Key **zonder passphrase** is handig voor VS Code; bescherm je Windows-account en schijf.
- Nieuwe machine: nieuwe key genereren en public key opnieuw in `authorized_keys` zetten.

---

## Zie ook

- `docs/VPS_DEPLOYMENT_RUNBOOK.md` — volledige VPS-deploy, env, systemd, QuantLog timer.
- `docs/OPERATOR_CHEATSHEET.md` — daily check, pull + restart, multi-repo.
- `docs/VPS_MULTI_MODULE_DEPLOYMENT.md` — QuantBuild + Bridge + QuantLog.
