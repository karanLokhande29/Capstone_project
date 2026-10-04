#!/usr/bin/env bash
# Deploy the comparator API as an Azure Function (Flex Consumption, Central India) and switch the public site to use it.
# Run it yourself from ui/ (it asks for the demo Gemini key once; the key is never written to a file):
#     bash api/deploy_function.sh
# Safe to re-run: it creates the Function App only if it does not exist yet.
set -euo pipefail
RG="rg-rbi-oblibench"
APP="rbiob-api-5qbvp2"
SA="rbioblibench5qbvp2"
SITE="https://rbioblibench5qbvp2.z29.web.core.windows.net"
cd "$(dirname "$0")/.."   # ui/

echo "1/7 Function App"
if ! az functionapp show -g "$RG" -n "$APP" -o none 2>/dev/null; then
  az functionapp create -g "$RG" -n "$APP" --storage-account "$SA" --flexconsumption-location centralindia \
    --runtime python --runtime-version 3.12 --instance-memory 2048 --maximum-instance-count 2 -o none
fi

echo "2/7 Package (bundle + server-side inputs; no tests, no full-text paragraphs)"
python3 api/build_bundle.py >/dev/null
python3 - <<'PY'
import zipfile
from pathlib import Path
api = Path("api")
files = ["function_app.py", "core.py", "jsonstream.py", "host.json", "requirements.txt", ".data/inputs.json"]
files += [str(p.relative_to(api)) for p in (api / "bundle").rglob("*") if p.is_file() and "__pycache__" not in p.parts]
with zipfile.ZipFile(".deploy-api.zip", "w", zipfile.ZIP_DEFLATED) as z:
    for f in files:
        z.write(api / f, f)
print(f"   {len(files)} files")
PY

echo "3/7 Settings (public mode, buffered responses, rate limit, CORS, replay store)"
CONN=$(az storage account show-connection-string -g "$RG" -n "$SA" --query connectionString -o tsv)
az functionapp config appsettings set -g "$RG" -n "$APP" -o none --settings \
  MODE=public STREAMING=buffered RATE_LIMIT_PER_MIN=6 ALLOWED_ORIGINS="$SITE" CACHE_CONNECTION="$CONN"
az functionapp cors add -g "$RG" -n "$APP" --allowed-origins "$SITE" -o none 2>/dev/null || true

echo "4/7 Demo Gemini key (paste, then Enter; nothing is shown)"
read -rs GKEY
az functionapp config appsettings set -g "$RG" -n "$APP" -o none --settings GEMINI_API_KEY="$GKEY"
unset GKEY

echo "5/7 Deploy code (remote build)"
az functionapp deployment source config-zip -g "$RG" -n "$APP" --src .deploy-api.zip --build-remote true -o none
rm -f .deploy-api.zip

echo "6/7 Copy the recorded hero replay (if any) to the replay store"
az storage container create --connection-string "$CONN" -n comparator-cache -o none
for f in api/.state/replays/*.json; do
  [ -e "$f" ] || continue
  az storage blob upload --connection-string "$CONN" -c comparator-cache -n "replays/$(basename "$f")" -f "$f" --overwrite -o none
done

HOST=$(az functionapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv)
echo "   health: $(curl -s "https://$HOST/api/health")"

echo "7/7 Rebuild and redeploy the public site against https://$HOST"
VITE_API_BASE="https://$HOST" npm run deploy:azure
echo "done: $SITE (API https://$HOST)"
