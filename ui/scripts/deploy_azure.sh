#!/usr/bin/env bash
# Deploy ui/dist-azure to the Azure Storage static website (rg-rbi-oblibench). Run from ui/ via `npm run deploy:azure`
# (which builds and runs check_dist first). Storage static websites do not compress, so JS, CSS and JSON are gzipped here
# and uploaded with Content-Encoding: gzip (HTML is tiny and stays plain). Every app route (including the 412 /case/<unit> pages) gets a copy of
# index.html so deep links return 200; the 404 document is the app too. The demo's JSON shards go under data/.
set -euo pipefail
export LC_ALL=C
SA="${AZURE_STORAGE_ACCOUNT:-rbioblibench5qbvp2}"
RG="${AZURE_RESOURCE_GROUP:-rg-rbi-oblibench}"
KEY=$(az storage account keys list -n "$SA" -g "$RG" --query "[0].value" -o tsv)
up() { az storage blob upload-batch -d '$web' --account-name "$SA" --account-key "$KEY" --overwrite -o none --only-show-errors "$@"; }

# 1. A gzipped copy of the build (same names), plus route copies of index.html.
GZ=.deploy-gz
rm -rf "$GZ" && cp -R dist-azure "$GZ"
# HTML stays uncompressed: index.html is also the 404 document, which the static website serves without Content-Encoding.
find "$GZ" -type f \( -name "*.js" -o -name "*.css" -o -name "*.json" \) -exec gzip -9 -n {} \; -exec sh -c 'mv "$1.gz" "$1"' _ {} \;
# "cases" and "lab" are also folders (cases/play, lab/edit), so they are uploaded one by one, not staged.
PARENTS="cases lab"
ROUTES="cases/failures cases/play cases/atlas lab/paste lab/edit triage results method present findings how-it-works trust demo"
STAGE=.routes-staging
rm -rf "$STAGE" && mkdir -p "$STAGE/case"
for r in $ROUTES $PARENTS; do mkdir -p "$STAGE/$(dirname "$r")"; done
for r in $ROUTES; do cp "$GZ/index.html" "$STAGE/$r"; done
python3 - "$STAGE" "$GZ" <<'PY'
import json, shutil, sys
from pathlib import Path
stage, gz = Path(sys.argv[1]), Path(sys.argv[2])
for u in json.loads(Path("dist-azure/data/cases/index.json").read_text())["units"]:
    shutil.copy(gz / "index.html", stage / "case" / u["id"])
PY

# 2. Upload: hashed assets are immutable; data shards are cached briefly; HTML is never cached.
# Content types are set explicitly: on gzipped bytes the CLI would guess application/octet-stream.
IMM="public, max-age=31536000, immutable"
up -s "$GZ" --pattern "assets/*.js" --content-type "text/javascript" --content-encoding gzip --content-cache-control "$IMM"
up -s "$GZ" --pattern "assets/*.css" --content-type "text/css" --content-encoding gzip --content-cache-control "$IMM"
up -s "$GZ" --pattern "assets/*.json" --content-type "application/json" --content-encoding gzip --content-cache-control "$IMM"
up -s "$GZ" --pattern "data/*" --content-type "application/json" --content-encoding gzip --content-cache-control "public, max-age=300"
up -s "$GZ" --pattern "index.html" --content-type "text/html" --content-encoding "" --content-cache-control "no-cache"
up -s "$STAGE" --content-type "text/html" --content-encoding "" --content-cache-control "no-cache"
for r in $PARENTS; do
  az storage blob upload -f "$GZ/index.html" -c '$web' -n "$r" --account-name "$SA" --account-key "$KEY" --overwrite \
    --content-type "text/html" --content-encoding "" --content-cache-control "no-cache" -o none --only-show-errors
done

# 3. Remove blobs that are no longer part of the site: stale assets, stale data shards, old route copies.
KEEP=$( (cd dist-azure && find assets data -type f; echo index.html; for r in $PARENTS; do echo "$r"; done; cd "../$STAGE" && find . -type f | sed 's#^\./##') | sort)
az storage blob list -c '$web' --account-name "$SA" --account-key "$KEY" --query "[].name" -o tsv --num-results "*" | sort > "$STAGE.remote"
comm -23 "$STAGE.remote" <(echo "$KEEP") | while IFS= read -r b; do
  [ -n "$b" ] && az storage blob delete -c '$web' -n "$b" --account-name "$SA" --account-key "$KEY" -o none --only-show-errors
done
rm -rf "$STAGE" "$STAGE.remote" "$GZ"
echo "deployed: $(az storage account show -n "$SA" -g "$RG" --query primaryEndpoints.web -o tsv)"
