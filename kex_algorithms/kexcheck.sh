#!/usr/bin/env bash
# Zeigt KEX-Algorithmen des lokalen SSH-Clients und des Remote-Hosts (z.B. Cisco Switch)
# Aufruf: ./kexcheck.sh <host> [port]

host="${1:?Aufruf: $0 <host> [port]}"
port="${2:-22}"

local_kex=$(ssh -Q kex | sort -u)

# Der Server schickt seine KEXINIT-Liste auch dann, wenn die Verhandlung scheitert
remote_kex=$(ssh -vv -p "$port" \
    -o BatchMode=yes \
    -o PreferredAuthentications=none \
    -o ConnectTimeout=5 \
    "probe@$host" 2>&1 \
  | awk '/peer server KEXINIT proposal/{f=1}
         f && /KEX algorithms:/{sub(/.*KEX algorithms: */,""); print; exit}' \
  | tr ',' '\n' | sort -u)

echo "=== Lokal: $(ssh -V 2>&1) ==="
echo "$local_kex"
echo
echo "=== Remote: $host:$port ==="
if [ -z "$remote_kex" ]; then
  echo "(keine KEX-Liste empfangen - Host nicht erreichbar oder Port falsch?)"
  exit 1
fi
echo "$remote_kex"
echo
echo "=== Gemeinsame Algorithmen ==="
common=$(comm -12 <(echo "$local_kex") <(echo "$remote_kex"))
echo "${common:-KEINE - das ist die Ursache der Fehlermeldung}"
