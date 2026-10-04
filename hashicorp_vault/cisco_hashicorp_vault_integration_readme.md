# Architekturkonzept: HashiCorp Vault Integration für Cisco Infrastruktur & Cisco ISE

Dieses Dokument beschreibt das Sicherheits- und Automatisierungskonzept zur Integration von **HashiCorp Vault** in Cisco-Netzwerkumgebungen (IOS-XE, NX-OS) sowie die synchrone Verwaltung von TACACS+ Shared Secrets mit **Cisco ISE**. 

Da Cisco-Betriebssysteme Vault-Engines nicht nativ anfragen können, übernimmt eine Automatisierungsplattform (z. B. **Ansible Automation Platform / AWX**) die Rolle des Orchestrators.

---

## 1. Gesamtarchitektur

HashiCorp Vault dient als zentrale **Single Source of Truth (SSOT)** für alle administrativen Zugangsdaten und Shared Secrets. Ansible fungiert als Brücke zwischen Vault, den Cisco-Netzwerkgeräten und Cisco ISE.

```
+-------------------------------------------------------------------+
|                         HashiCorp Vault                           |
|                    (KV-v2 Secrets Engine)                         |
+-------------------------------------------------------------------+
                             ^         ^
              AppRole Auth / |         | AppRole Auth /
              Read/Write     |         | Read/Write
                             v         v
+-------------------------------------------------------------------+
|                     Ansible Automation Platform                   |
+-------------------------------------------------------------------+
                 /                             \
  SSH / NETCONF /                               \ REST API (ERS/OpenAPI)
               v                                 v
+---------------------------+       +-------------------------------+
|    Cisco Network Device   | <---> |           Cisco ISE           |
| (IOS-XE / NX-OS - Client) | TACACS|  (Identity Services Engine)   |
+---------------------------+       +-------------------------------+
```

---

## 2. Passwortsicherheit & Governance

Um höchste Sicherheitsstandards zu erfüllen, gelten für die Infrastruktur folgende Richtlinien:

* **Zentralisierung in Vault KV-v2:** Alle Zugangsdaten liegen verschlüsselt (AES-256-GCM) in der Key-Value v2 Engine. Diese bietet eine lückenlose Versionierung und Historisierung aller Passwortänderungen.
* **Maschinelle Authentifizierung via AppRole:** Ansible verwendet keine statischen Master-Tokens. Die Authentifizierung erfolgt dynamisch über die Vault AppRole (`RoleID` und eine kurzlebige `SecretID`).
* **Prinzip der kleinsten Rechte (Least Privilege):** Die Ansible-AppRole erhält per Vault-Policy exklusiv Lese- und Schreibrechte auf den Pfad der Netzwerkgeräte (z. B. `secret/data/network/cisco/*`).
* **Speicherschutz (No-Log Policy):** Zugangsdaten werden von Ansible ausschließlich im Arbeitsspeicher gehalten. Sämtliche Ansible-Tasks, die Secrets verarbeiten, müssen mit Schutzmechanismen zur Unterdrückung von Log-Ausgaben konfiguriert sein, um Leaks im Ausführungs-Log zu verhindern.
* **Komplexitätsanforderungen:** Automatisch generierte Passwörter und Shared Secrets weisen eine Länge von mindestens 32 bis 64 Zeichen auf (alphanumerisch inkl. Sonderzeichen, ausgenommen gerätespezifische Break-Characters wie `?` oder `"`).

---

## 3. Konzept für den regelmäßigen Passwortwechsel (Rotation)

Der Rotations-Lifecycle läuft vollautomatisiert über geplante Aufträge ab und folgt einem **Fail-Safe-Verfahren** (Transaction Safety), um Aussperrungen zu vermeiden:

1. **Aktuellen Status abfragen:** Ansible liest die bestehenden Zugangsdaten des Geräts aus Vault aus.
2. **Verbindung aufbauen:** Verbindung zum Cisco-Gerät via SSH/NETCONF unter Nutzung der aktuellen Zugangsdaten.
3. **Neues Secret generieren:** Lokale Erzeugung eines neuen, kryptografisch sicheren Zufallspassworts im Ansible-Arbeitsspeicher.
4. **Auf Cisco-Gerät anwenden:** Einspielen des neuen Passworts auf dem Gerät und Sichern der Konfiguration im NVRAM.
5. **Verbindung verifizieren:** Aufbau einer neuen, parallelen Test-Sitzung zum Gerät mit den neuen Zugangsdaten.
6. **Vault aktualisieren:** Erst nach erfolgreicher Verifikation schreibt Ansible die neuen Zugangsdaten als neue Version in die Vault KV-v2 Engine.
7. **Fehlerbehandlung / Rollback:** Schlägt die Verifikation fehl, bleibt der bestehende Vault-Eintrag unverändert und es wird ein Incident-Alert ausgelöst.

---

## 4. Umsetzung der lokalen Passwort-Rotation mit Ansible

Für die Umsetzung werden offizielle Ansible Collections genutzt. Es werden keine Zugangsdaten oder Skripte fest auf den Steuerungs-Knoten hinterlegt.

### Benötigte Ansible Collections
* **`community.hashi_vault`:** Ermöglicht die sichere Interaktion mit den KV-v2 Engines und das Authentifizieren via AppRole.
* **`cisco.ios` / `cisco.nxos`:** Stellt Module für das Benutzermanagement und das Speichern der Konfiguration auf Cisco-Betriebssystemen bereit.

### Abfolge des Ansible-Playbooks zur Passwort-Rotation
Das Playbook gliedert sich in folgende logische Schritte:

1. **Vault-Authentifizierung & Abruf:** Ansible liest über das `vault_kv2_get`-Modul die aktuellen Zugangsdaten des Zielgeräts unter Verwendung der Umgebungsvariablen für RoleID und SecretID aus.
2. **Verbindungsaufbau:** Die aus Vault gelesenen Daten werden dynamisch als Verbindungsparameter (`ansible_user`, `ansible_password`) für das Zielgerät gesetzt.
3. **Generierung:** Ein neues, 32 Zeichen altes Passwort wird über ein Zufalls-Lookup im Speicher generiert.
4. **Geräte-Update:** Das Modul `cisco.ios.ios_user` aktualisiert den Benutzereintrag auf dem Cisco-Switch mit dem neuen Passwort und der höchsten Privilegienstufe (Privilege 15).
5. **Konfigurationssicherung:** Das Modul `cisco.ios.ios_config` führt eine Konfigurationsspeicherung (`write memory`) durch.
6. **Verifikation:** Ansible prüft die Port-Erreichbarkeit und SSH-Reaktion des Geräts.
7. **Vault-Update:** Das neue Passwort wird zusammen mit einem ISO-Zeitstempel der Rotation über das Modul `community.hashi_vault.vault_kv2_write` als neue Version in Vault abgelegt.

---

## 5. Dynamische Verwaltung von TACACS+ Shared Secrets mit Cisco ISE

Die Verwaltung von TACACS+ Shared Secrets erfordert eine **synchrone Aktualisierung** auf dem AAA-Server (Cisco ISE) und auf allen Network Access Devices (NADs).

### Ablauf der TACACS+ Secret Rotation

1. **Secret Erzeugung:** Ansible generiert ein hochkomplexes Shared Secret (64 Zeichen).
2. **Cisco ISE Update (Server First):** Ansible kontaktiert die Cisco ISE REST API und aktualisiert den TACACS+-Schlüssel des betreffenden Netzwerkgeräts.
3. **Cisco Device Update (Client Second):** Ansible verbindet sich mit dem Cisco-Gerät und aktualisiert die `tacacs server`-Konfiguration.
4. **Funktionstest:** Ansible führt über das CLI einen simulierten AAA-Testbefehl aus (`test aaa group tacacs+`), um sicherzustellen, dass die Verschlüsselung zwischen Switch und ISE übereinstimmt.
5. **Konfigurationsspeicherung:** Nach erfolgreichem Test wird die Konfiguration auf dem Cisco-Gerät permanent gespeichert.
6. **Vault Dokumentation:** Das neue Shared Secret wird in Vault im zugewiesenen Pfad abgelegt.

### Cisco ISE Schnittstelle
Cisco ISE bietet zur Verwaltung von Netzwerkgeräten die **ERS API** (External RESTful Services) sowie ab Version 3.1+ die **Open API**. 
* Der Zugriff erfolgt über HTTPS auf Port 9060 (`/ers/config/networkdevice`).
* Die Identifizierung des Geräts erfolgt über dessen eindeutige ISE Resource ID.
* Das Feld `tacacsAuthenticationSettings.sharedSecret` wird mittels REST PUT-Request mit dem neuen Secret überschrieben.

### Abfolge des Ansible-Playbooks für TACACS+ / ISE
Das Playbook führt folgende Schritte aus:

1. **Secret Generation:** Erzeugung eines 64-stelligen alphanumerischen Schlüssels.
2. **ISE Device Lookup:** Über einen HTTP-GET-Request an die ERS-Schnittstelle von Cisco ISE wird die eindeutige ID des Switches anhand seines Hostnamens ermittelt.
3. **ISE Update:** Ein HTTP-PUT-Request sendet die aktualisierte JSON-Struktur mit dem neuen `sharedSecret` an die ISE-API.
4. **Switch Update:** Über das Cisco IOS Configuration Modul wird der TACACS-Server-Eintrag auf dem Switch mit dem neuen Schlüssel aktualisiert.
5. **AAA Validation:** Ein Test-Befehl auf der CLI prüft die Antwort des ISE-Servers. Eine Rückmeldung (auch eine kontrollierte Ablehnung falscher Test-Credentials) bestätigt, dass der Shared Key auf beiden Seiten korrekt ist.
6. **Sicherung:** Speichern der Laufzeitkonfiguration auf dem Switch.
7. **Vault-Aktualisierung:** Der neue TACACS-Key wird zusammen mit dem Rotationsdatum in der Vault KV-v2 Engine gesichert.

---

## 6. Betriebs- und Sicherheitsempfehlungen

| Thema | Empfohlene Maßnahme |
| :--- | :--- |
| **Break-Glass Access** | Einrichtung eines lokalen Notfall-Users (`breakglass`) auf den Switches. Dessen Passwort verbleibt in einem speziell geschützten Vault-Pfad mit Mehr-Augen-Prinzip (Vault Control Groups / Approval Workflows). |
| **Zero-Downtime bei ISE** | Cisco ISE synchronisiert Network Device Secrets intern vom Primary Admin Node (PAN) zu allen Policy Service Nodes (PSNs). Bei der Automatisierung sollte eine kurze Pufferzeit (~2–5 Sekunden) für die interne ISE-Replikation eingeplant werden. |
| **Einzel-Secrets vs. Gruppen-Secrets** | Jedes Netzwerkgerät sollte ein individuelles TACACS+ Shared Secret erhalten, um Lateral Movement im Falle einer Geräte-Kompromittierung zu verhindern. |
| **Audit Logging** | Alle Lese- und Schreibzugriffe auf Vault sowie alle REST-API-Zugriffe auf Cisco ISE werden an ein zentrales SIEM (z. B. Splunk, ELK) weitergeleitet. |