# Umstellung von Portainer auf Arcane

Stand: November 2026, Arcane 2.x (Image `ghcr.io/getarcaneapp/manager:v2`).
Grundprinzip: **Die laufenden Container bleiben unangetastet.** Beide Tools sprechen mit demselben Docker-Daemon, deshalb können Portainer und Arcane parallel laufen und Stack für Stack umgezogen werden. Portainer wird erst am Ende abgeschaltet.

## Wichtige Warnungen vorab

- **Stacks nie in der Portainer-UI löschen.** „Remove stack“ führt ein `down` aus und entfernt die Container. Zum Abschalten nur den Portainer-Container selbst stoppen.
- **Volumes nie mit `docker volume prune` oder `docker compose down -v` anfassen**, solange nicht alles verifiziert ist.
- Das Portainer-Volume `portainer_data` mindestens 30 Tage als Rückfallebene behalten.
- **Ein Redeploy in Arcane kann neue Images ziehen und Container neu erstellen.** Vor dem Umzug eines Stacks Image-Tags pinnen oder die Hinweise in Phase 3 beachten.

## Voraussetzung: Docker Compose v2

Die Compose-Dateien dieser Anleitung nutzen die aktuelle Compose Specification (u. a. `name:` und `cgroup:`). Dafür wird das Plugin `docker compose` (mit Leerzeichen) gebraucht. Das alte `docker-compose` (v1, mit Bindestrich) ist veraltet und bricht mit Meldungen wie `Unsupported config option for services.arcane: 'cgroup'` oder `'name' does not match any of the regexes` ab.

```bash
docker compose version        # muss v2.x oder höher zeigen
docker-compose version        # v1.x = veraltet, nicht mehr verwenden
```

Plugin installieren, falls es fehlt:

```bash
# Variante A: Distributionspaket (Ubuntu 24.04+, Debian 13+)
sudo apt-get update
sudo apt-get install -y docker-compose-v2

# Variante B: "E: Unable to locate package docker-compose-plugin" -> Docker-Repository einbinden.
# Die vorhandene Docker-Engine bleibt unverändert, es wird nur das Plugin installiert.
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
. /etc/os-release
sudo curl -fsSL https://download.docker.com/linux/$ID/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID ${UBUNTU_CODENAME:-$VERSION_CODENAME} stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-compose-plugin

# Altes v1 danach entfernen
sudo apt-get remove -y docker-compose
```

In Skripten und Playbooks `docker-compose` durch `docker compose` ersetzen. Laufende Container und Projekte bleiben beim Wechsel erhalten. Der Dateiname `docker-compose.yaml` statt `compose.yaml` funktioniert mit v2 genauso.

## Phase 0 – Bestandsaufnahme

```bash
# Alle Compose-Projekte inkl. Pfad der Compose-Datei (Portainer-Stacks liegen unter /data/compose/<ID>/)
docker compose ls -a

# Container ohne Compose-Projekt (= "Standalone", keine Stack-Datei vorhanden)
docker ps -a --format '{{.Names}}\t{{.Label "com.docker.compose.project"}}' | awk -F'\t' '$2==""'

# Portainer selbst
docker inspect portainer --format '{{.Config.Image}} {{range .Mounts}}{{.Name}}:{{.Destination}} {{end}}'
```

Notieren, was **nicht** automatisch umzieht (liegt in der Portainer-Datenbank):

| Portainer-Objekt | Vorgehen in Arcane |
|---|---|
| Stacks (Compose-Dateien) | Dateien exportieren, siehe Phase 3 |
| Stack-Umgebungsvariablen | aus `stack.env` bzw. aus der UI übernehmen, in `.env` ablegen |
| Benutzer, Teams, Rollen | in Arcane neu anlegen oder per OIDC/SSO anbinden |
| Registry-Zugangsdaten | in Arcane neu hinterlegen (neue Secrets, nicht kopieren) |
| Custom Templates, Webhooks | durch GitOps bzw. Arcane-API ersetzen |
| Weitere Environments / Agents | in Arcane als Environment mit `arcane-agent` neu anlegen |

## Phase 1 – Backup

```bash
# Portainer-Backup über UI: Settings > Backup configuration > Download backup file
# Zusätzlich das komplette Datenvolumen sichern:
sudo mkdir -p /opt/backups
docker run --rm -v portainer_data:/data -v /opt/backups:/backup alpine \
  tar czf /backup/portainer_data-$(date +%F).tar.gz -C /data .

# Docker-Zustand dokumentieren
docker ps -a > /opt/backups/docker-ps-$(date +%F).txt
```

Vor dem Umzug eines Stacks zusätzlich festhalten, **wo seine Daten liegen** (wichtig für Datenbanken):

```bash
docker inspect <db-container> --format '{{range .Mounts}}{{.Type}} {{.Name}} {{.Source}} -> {{.Destination}}{{"\n"}}{{end}}'
```

Für den Datenpfad der Datenbank (z. B. `/var/lib/postgresql/data`) muss ein Volume oder Host-Pfad erscheinen. Nur dann bleiben die Daten erhalten, wenn der Container neu erstellt wird.

## Phase 2 – Arcane in Betrieb nehmen

```bash
sudo mkdir -p /opt/arcane /opt/stacks
cd /opt/arcane
# compose.yaml und .env.example aus dieser Lieferung hierher kopieren
cp .env.example .env
chmod 600 .env
sed -i "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=$(openssl rand -hex 32)|" .env
# APP_URL, PUID, PGID in .env anpassen (PUID/PGID = Besitzer von /opt/stacks, siehe "Berechtigungen")

docker compose up -d
docker compose ps                         # Status "healthy" abwarten
curl -s http://localhost:3552/health
```

- UI: `http://<server>:3552`, Erstanmeldung `arcane` / `arcane-admin`. Das Passwort muss sofort geändert werden.
- Port 3552 läuft parallel zu Portainer (9000/9443), es gibt keinen Konflikt.
- **`ENCRYPTION_KEY` und das Volume `arcane-data` sichern.** Ohne den Schlüssel sind verschlüsselt gespeicherte Daten nicht mehr lesbar.
- Gehärtete Variante mit Socket-Proxy: `compose.socketproxy.yaml`.

### Berechtigungen: PUID/PGID und /opt/stacks

Arcane läuft im Container mit der UID/GID aus `PUID`/`PGID` (Standard 1000) und muss die Dateien in `/opt/stacks` lesen und schreiben können. Passt der Besitzer nicht, erscheint in Arcane: `Failed to load project … open /opt/stacks/<name>/compose.yaml: permission denied`.

```bash
id                                            # eigene UID/GID
grep -E '^(PUID|PGID)=' /opt/arcane/.env      # Werte von Arcane
ls -ln /opt/stacks/<name>                     # Besitzer der Stack-Dateien
```

Beheben (Beispiel mit 1000:1000, Werte aus der `.env` einsetzen):

```bash
sudo chown -R 1000:1000 /opt/stacks
sudo find /opt/stacks -type d -exec chmod 755 {} +
sudo find /opt/stacks -type f -exec chmod 644 {} +
sudo find /opt/stacks \( -name '.env' -o -name 'stack.env' \) -exec chmod 600 {} +
```

Alternativ `PUID`/`PGID` in `/opt/arcane/.env` auf die Werte von `id -u` / `id -g` setzen und `docker compose up -d --force-recreate` ausführen. Kontrolle im Container: `docker exec arcane id` und `docker exec arcane ls -l /opt/stacks/<name>`.

## Phase 3 – Stacks übernehmen (einzeln, unkritische zuerst)

Arcane verwaltet Compose-Projekte aus `/opt/stacks/<name>/`. Der Verzeichnisname soll dem bisherigen Projektnamen entsprechen (siehe `docker compose ls`), damit Compose die laufenden Container als dieselbe Anwendung erkennt.

### 3.1 Portainer-IDs den Stacknamen zuordnen

Portainer legt jeden Stack unter einer Nummer ab. Zeigt `ls` nur `1  2`, sind das die IDs zweier Stacks.

```bash
VOL=$(docker volume inspect portainer_data -f '{{.Mountpoint}}')
sudo ls -la "$VOL/compose/1" "$VOL/compose/2"      # je eine docker-compose.yml, ggf. stack.env
```

Welche ID zu welchem Stack gehört, erkennst du so (ein Weg genügt):

- **Portainer-UI:** Stacks > Stack anklicken, die ID steht in der Adresszeile (`…/stacks/<name>?id=2`).
- **Kommando:** `docker compose ls -a`. Spalte `NAME` ist der Stackname, in `CONFIG FILES` steht z. B. `/data/compose/1/docker-compose.yml`, die Zahl ist die ID.
- **Inhalt:** `sudo head -20 "$VOL/compose/1/docker-compose.yml"` und Images/Container-Namen vergleichen.

### 3.2 Dateien kopieren

Pro Stack `STACK` (Name) und `ID` (Zahl) setzen und den Block ausführen. Beispiel: ID 1 = `nautobot`.

```bash
VOL=$(docker volume inspect portainer_data -f '{{.Mountpoint}}')
STACK=nautobot ; ID=1                       # anpassen, danach für den nächsten Stack wiederholen
OWNER=1000:1000                             # = PUID:PGID aus /opt/arcane/.env

sudo mkdir -p /opt/stacks/$STACK
sudo cp "$VOL/compose/$ID/docker-compose.yml" /opt/stacks/$STACK/compose.yaml
# Variablen: in neueren Portainer-Versionen liegt eine stack.env im selben Ordner
if [ -f "$VOL/compose/$ID/stack.env" ]; then
  sudo cp "$VOL/compose/$ID/stack.env" /opt/stacks/$STACK/stack.env
  sudo cp "$VOL/compose/$ID/stack.env" /opt/stacks/$STACK/.env
fi
sudo chown -R $OWNER /opt/stacks/$STACK
sudo chmod 644 /opt/stacks/$STACK/compose.yaml
sudo chmod 600 /opt/stacks/$STACK/.env /opt/stacks/$STACK/stack.env 2>/dev/null
```

Wichtig: `OWNER` muss **`PUID:PGID` von Arcane** sein. Nur wenn dein eigener Benutzer dieselbe UID hat, ist `$(id -u):$(id -g)` richtig.

Falls Variablen nur in der Portainer-UI stehen: dort kopieren (Stack > Environment variables) und in `/opt/stacks/$STACK/.env` einfügen (`chmod 600`).

### 3.3 Vor dem ersten Deploy prüfen

1. In `compose.yaml` oben `name: <stackname>` ergänzen, falls der Verzeichnisname vom Projektnamen abweicht.
2. Relative Pfade (`./data:/…`) und `env_file:` kontrollieren. Portainer hat die Datei in seinem eigenen Ordner ausgeführt, relative Pfade können jetzt woanders auflösen.
3. Syntax testen: `docker compose -f /opt/stacks/$STACK/compose.yaml config -q && echo OK`. Fehlen Variablen, fehlt die `.env`.
4. **Image-Tags prüfen.** Tags wie `postgres:15-alpine` oder `redis:7-alpine` sind beweglich. Ein Deploy in Arcane kann neuere Images ziehen, wodurch Container neu erstellt werden. Bei gleicher Major-Version ist das meist unkritisch, bei Datenbanken aber immer Backup vorher. Soll sich nichts ändern: feste Tags (inkl. Patch-Version) eintragen, oder den Stack einmalig per CLI starten:

   ```bash
   cd /opt/stacks/$STACK && docker compose up -d --pull never
   ```

Dieser Schritt kopiert nur Dateien. An den laufenden Containern ändert sich erst etwas, wenn du in Arcane deployst.

### 3.4 In Arcane übernehmen und kontrollieren

In Arcane **Projects** öffnen, das Projekt sollte mit dem laufenden Zustand erscheinen. Dann **Up/Redeploy** auslösen. Stimmt die Konfiguration nicht exakt mit der laufenden überein oder gibt es neue Images, erstellt Compose die Container neu (kurze Downtime). Deshalb Wartungsfenster einplanen und pro Stack prüfen:

```bash
docker compose ls                               # Projekt erscheint mit Pfad /opt/stacks/<name>
docker compose -p $STACK ps -a                  # alle Services, auch beendete
docker inspect <container> --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}'
```

Danach in der Anwendung selbst anmelden und Daten stichprobenartig prüfen.

**Init-Container und die Meldung `failed to deploy project: container <name>-init exited (0)`:** Viele Stacks (z. B. Nautobot) enthalten Einmal-Jobs, die Migrationen oder Setup erledigen und danach beenden. Exit-Code 0 heißt erfolgreich beendet. Arcane kann das beim Deploy trotzdem als Fehler melden. Prüfen:

```bash
docker logs <stack>-init --tail 30              # sollte ohne Fehler enden
docker compose -p $STACK ps -a                  # Hauptdienste "running/healthy", Init "exited (0)"
```

Sind die Hauptdienste gesund, kann die Meldung ignoriert werden. Wer sie vermeiden will, startet den Stack per `docker compose up -d` auf der CLI. Updates und Neustarts sind weiterhin in Arcane möglich.

**Standalone-Container** (ohne Compose-Projekt) bleiben in Arcane start-/stoppbar. Langfristig besser in eine Compose-Datei überführen (`docker inspect` als Vorlage) und als Projekt anlegen.

## Phase 4 – Funktionen in Arcane einrichten

- **Benutzer/SSO:** Settings > Authentication. Bei OIDC lokalen Login erst abschalten, wenn der IdP-Login getestet ist. Notfallzugang: `/login/backup`.
- **Reverse Proxy:** WebSocket-Upgrade-Header zwingend weiterreichen; `APP_URL` auf die öffentliche URL setzen und `TRUSTED_PROXIES` eintragen.
- **Remote-Hosts:** Environments > Add Environment (Direct: Port 3553, oder Edge ohne eingehenden Port), dort wird das Agent-Snippet erzeugt. Entspricht den Portainer-Agents.
- **Auto-Updates:** nur mit Update-Delay (z. B. 72 h) für internet-nahe Dienste.
- **Backups:** `arcane-data` und `/opt/stacks` in die bestehende Sicherung aufnehmen, `.env`-Dateien nur verschlüsselt ablegen.

## Phase 5 – Parallelbetrieb und Abschaltung von Portainer

Mindestens 1–2 Wochen beide Tools parallel laufen lassen. Dann:

```bash
docker stop portainer          # nur den Container, KEINE Stacks in der UI löschen
# Remote-Hosts: Portainer-Agent / Edge-Agent dort ebenfalls stoppen
```

Nach weiteren ~30 Tagen ohne Probleme:

```bash
docker rm portainer
docker volume rm portainer_data      # erst nach geprüftem Backup aus Phase 1
docker image rm portainer/portainer-ce
```

## Fehlerbehebung

| Meldung | Ursache und Lösung |
|---|---|
| `Unsupported config option for services.arcane: 'cgroup'` / `'name' does not match any of the regexes` | Veraltetes `docker-compose` v1. Auf `docker compose` (v2) wechseln, siehe „Voraussetzung“. |
| `E: Unable to locate package docker-compose-plugin` | Docker-Repository fehlt. Variante B unter „Voraussetzung“ ausführen. |
| `Failed to load project … permission denied` | Besitzer von `/opt/stacks/<name>` passt nicht zu `PUID`/`PGID`. Siehe „Berechtigungen“. |
| `failed to deploy project: container …-init exited (0)` | Einmal-Job erfolgreich beendet, kein Fehler. Siehe Phase 3.4. |
| Container wurden beim Deploy neu erstellt | Neue Images oder abweichende Konfiguration. Tags pinnen, `--pull never`, Datenpfade vorher prüfen (Phase 1). |

## Rollback

Läuft ein Stack nach der Übernahme nicht sauber: Compose-Datei in `/opt/stacks/<name>` mit der Sicherung aus `portainer_data` vergleichen und den Stack wie vorher starten. Portainer selbst ist bis zur Abschaltung unverändert: `docker start portainer` genügt. Arcane lässt sich jederzeit mit `docker compose down` (ohne `-v`) beenden, die verwalteten Container laufen weiter.

## Betrieb und Updates

```bash
cd /opt/arcane
docker compose pull && docker compose up -d     # Update innerhalb von v2
# Rollback: Image-Tag in compose.yaml auf die vorherige Version setzen (z. B. v2.16.1), dann dieselben Befehle
docker compose logs -f arcane
```

## Optional: Ausrollen mit Ansible

```yaml
- name: Arcane ausrollen
  hosts: docker_hosts
  become: true
  vars:
    arcane_dir: /opt/arcane
  tasks:
    - name: Verzeichnisse anlegen
      ansible.builtin.file:
        path: "{{ item }}"
        state: directory
        mode: "0755"
      loop:
        - "{{ arcane_dir }}"
        - /opt/stacks

    - name: compose.yaml ablegen
      ansible.builtin.copy:
        src: compose.yaml
        dest: "{{ arcane_dir }}/compose.yaml"
        mode: "0644"

    - name: .env ablegen (Schlüssel aus Ansible Vault)
      ansible.builtin.copy:
        dest: "{{ arcane_dir }}/.env"
        mode: "0600"
        content: |
          ENCRYPTION_KEY={{ vault_arcane_encryption_key }}
          APP_URL=https://arcane.example.org
          PUID=1000
          PGID=1000

    - name: Arcane starten
      community.docker.docker_compose_v2:
        project_src: "{{ arcane_dir }}"
        state: present
```

## Abnahme-Checkliste

- [ ] `docker compose version` zeigt v2, altes `docker-compose` entfernt
- [ ] Portainer-Backup und `portainer_data`-Archiv vorhanden
- [ ] Arcane `healthy`, Standardpasswort geändert, `ENCRYPTION_KEY` gesichert
- [ ] `PUID`/`PGID` passen zum Besitzer von `/opt/stacks`
- [ ] Datenpfade (Volumes/Bind-Mounts) der Datenbanken vor dem Umzug dokumentiert
- [ ] Jeder Stack als Projekt in Arcane sichtbar, Hauptdienste laufen, Variablen vorhanden, Anwendung getestet
- [ ] Benutzer/SSO, Registries, Remote-Hosts neu eingerichtet
- [ ] Reverse Proxy/TLS und `TRUSTED_PROXIES` getestet
- [ ] Arcane-Daten und `/opt/stacks` in der Sicherung
- [ ] Portainer gestoppt, Aufbewahrungsfrist für das Volume notiert
