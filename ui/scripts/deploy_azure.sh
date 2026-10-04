#!/usr/bin/env bash
# Deploy ui/dist-azure to the Azure Storage static website (rg-rbi-oblibench). Run from ui/ after `npm run build:azure`.
# Every app route (including the 412 /case/<unit> pages) gets a copy of index.html so deep links return 200; the 404
# document is the app too. The demo's JSON shards go under data/.
set -euo pipefail
SA="${AZURE_STORAGE_ACCOUNT:-rbioblibench5qbvp2}"
RG="${AZURE_RESOURCE_GROUP:-rg-rbi-oblibench}"
KEY=$(az storage account keys list -n "$SA" -g "$RG" --query "[0].value" -o tsv)
up() { az storage blob upload-batch -d '$web' --account-name "$SA" --account-key "$KEY" --overwrite -o none --only-show-errors "$@"; }

up -s dist-azure --pattern "assets/*" --content-cache-control "public, max-age=31536000, immutable"
up -s dist-azure --pattern "data/*" --content-cache-control "public, max-age=300"
up -s dist-azure --pattern "index.html" --content-cache-control "no-cache"

# Route copies of index.html, staged as files named like the URL path and uploaded in one batch.
export LC_ALL=C
# "cases" and "lab" are also folders (cases/play, lab/edit), so they are uploaded one by one, not staged.
PARENTS="cases lab"
ROUTES="cases/failures cases/play cases/atlas lab/paste lab/edit triage results method present findings how-it-works trust demo"
STAGE=.routes-staging
rm -rf "$STAGE" && mkdir -p "$STAGE/case"
for r in $ROUTES; do mkdir -p "$STAGE/$(dirname "$r")"; cp dist-azure/index.html "$STAGE/$r"; done
python3 - "$STAGE" <<'PY'
import json, shutil, sys
from pathlib import Path
stage = Path(sys.argv[1])
for u in json.loads(Path("dist-azure/data/cases/index.json").read_text())["units"]:
    shutil.copy("dist-azure/index.html", stage / "case" / u["id"])
PY
up -s "$STAGE" --content-type "text/html" --content-cache-control "no-cache"
for r in $PARENTS; do
  az storage blob upload -f dist-azure/index.html -c '$web' -n "$r" --account-name "$SA" --account-key "$KEY" --overwrite \
    --content-type "text/html" --content-cache-control "no-cache" -o none --only-show-errors
done

# Remove blobs that are no longer part of the site: stale assets, stale data shards, old route copies.
KEEP=$( (cd dist-azure && find assets data -type f; echo index.html; for r in $PARENTS; do echo "$r"; done; cd "../$STAGE" && find . -type f | sed 's#^\./##') | sort)
az storage blob list -c '$web' --account-name "$SA" --account-key "$KEY" --query "[].name" -o tsv --num-results "*" | sort > "$STAGE.remote"
comm -23 "$STAGE.remote" <(echo "$KEEP") | while IFS= read -r b; do
  [ -n "$b" ] && az storage blob delete -c '$web' -n "$b" --account-name "$SA" --account-key "$KEY" -o none --only-show-errors
done
rm -rf "$STAGE" "$STAGE.remote"
echo "deployed: $(az storage account show -n "$SA" -g "$RG" --query primaryEndpoints.web -o tsv)"
