#!/usr/bin/env bash
# Deploy the hosted audit generator (ui/api_audit) as an Azure Function (Flex Consumption, Central India) and point the
# public site at it. Run from the repository root:
#     bash ui/api_audit/deploy.sh
#
# Zero-charge setup (Karan's rule: nothing may be charged):
# - Azure for Students has its spending limit on, so no card can be charged; on top of that the app runs on one
#   on-demand instance with no always-ready instances (nothing billed while idle), and the service caps itself at
#   AUDIT_GENERATE_DAILY_CAP=40 packs and AUDIT_AI_DAILY_CAP=30 AI answers per day, which keeps even full daily use
#   inside the free monthly Flex Consumption allowance (100,000 GB-s).
# - Gemini: paste a key from a Google AI Studio project WITHOUT billing (free tier). A free-tier key cannot be billed;
#   when its quota runs out the assistant says so and stops until the quota resets. Press Enter without a key to deploy
#   with the AI assistant off (generate, review and exports still work). The key is never printed or written to a file.
# - The Lab's live comparator (VITE_API_BASE) is left off, as on the current site, because its key's billing is unknown.
#
# Needs: `az login`, the models and vectors (scripts/auditgen_hosted_models.py export / vectors) and the capped sample
# packs (ui/scripts/build_public_extras.py). Safe to re-run. `--code-only` redeploys the code and the site and leaves the
# app, its settings and the key as they are; `--api-only` redeploys the service code only.
set -euo pipefail
CODE_ONLY="${1:-}"
RG="rg-rbi-oblibench"
APP="rbiob-audit-5qbvp2"
SA="rbioblibench5qbvp2"
SITE="https://rbioblibench5qbvp2.z29.web.core.windows.net"
cd "$(dirname "$0")/../.."   # repository root

if [ "$CODE_ONLY" != "--code-only" ] && [ "$CODE_ONLY" != "--api-only" ]; then
echo "1/6 Function App (one on-demand instance, nothing always-ready)"
if ! az functionapp show -g "$RG" -n "$APP" -o none 2>/dev/null; then
  az functionapp create -g "$RG" -n "$APP" --storage-account "$SA" --flexconsumption-location centralindia \
    --runtime python --runtime-version 3.12 --instance-memory 4096 --maximum-instance-count 1 -o none
fi
az functionapp scale config set -g "$RG" -n "$APP" --maximum-instance-count 1 -o none

echo "2/6 Settings"
echo "   Paste a FREE-TIER Gemini API key (Google AI Studio project with no billing), then Enter."
echo "   Nothing is shown while you type. Press Enter alone to deploy without the AI assistant."
read -rs GKEY
echo
CONN=$(az storage account show-connection-string -g "$RG" -n "$SA" --query connectionString -o tsv)
az functionapp config appsettings set -g "$RG" -n "$APP" -o none --settings \
  AUDIT_STORE_CONNECTION="$CONN" AUDIT_GEMINI_API_KEY="$GKEY" ALLOWED_ORIGINS="$SITE" \
  AUDIT_GENERATE_DAILY_CAP=40 AUDIT_AI_DAILY_CAP=30 >/dev/null
unset GKEY CONN
az functionapp cors add -g "$RG" -n "$APP" --allowed-origins "$SITE" -o none 2>/dev/null || true

echo "3/6 Generated packs are deleted after 7 days"
cat > .deploy-policy.json <<'JSON'
{"rules": [{"enabled": true, "name": "auditgen-packs-7d", "type": "Lifecycle",
  "definition": {"actions": {"baseBlob": {"delete": {"daysAfterModificationGreaterThan": 7}}},
                 "filters": {"blobTypes": ["blockBlob"], "prefixMatch": ["auditgen-packs/"]}}}]}
JSON
az storage account management-policy create --account-name "$SA" -g "$RG" --policy @.deploy-policy.json -o none
rm -f .deploy-policy.json
fi

echo "4/6 Package (capped sample packs first: the service ships them)"
python3 ui/scripts/build_public_extras.py >/dev/null
python3 ui/api_audit/package.py

echo "5/6 Deploy code (remote build, 5-10 minutes)"
az functionapp deployment source config-zip -g "$RG" -n "$APP" --src ui/api_audit/.build/auditgen-api.zip --build-remote true -o none

HOST=$(az functionapp show -g "$RG" -n "$APP" --query defaultHostName -o tsv 2>/dev/null || true)
[ -n "$HOST" ] || HOST="$APP.azurewebsites.net"
echo "   health: $(curl -s "https://$HOST/api/auditgen/health")"

[ "$CODE_ONLY" = "--api-only" ] && { echo "done (service only)"; exit 0; }
echo "6/6 Rebuild and redeploy the public site against https://$HOST"
cd ui
VITE_AUDIT_API="https://$HOST" npm run deploy:azure
echo "done: $SITE/auditgen (API https://$HOST)"
