#!/usr/bin/env bash
# Deploy ui/dist-azure to the Azure Storage static website (rg-rbi-oblibench). Run from ui/ after `npm run build:azure`.
# Every app route also gets a copy of index.html so deep links return 200 (the 404 document is the app too).
set -euo pipefail
SA="${AZURE_STORAGE_ACCOUNT:-rbioblibench5qbvp2}"
RG="${AZURE_RESOURCE_GROUP:-rg-rbi-oblibench}"
KEY=$(az storage account keys list -n "$SA" -g "$RG" --query "[0].value" -o tsv)
az storage blob upload-batch -s dist-azure -d '$web' --account-name "$SA" --account-key "$KEY" --overwrite \
  --pattern "assets/*" --content-cache-control "public, max-age=31536000, immutable" -o none --only-show-errors
az storage blob upload-batch -s dist-azure -d '$web' --account-name "$SA" --account-key "$KEY" --overwrite \
  --pattern "index.html" --content-cache-control "no-cache" -o none --only-show-errors
ROUTES="findings demo how-it-works trust"
for r in $ROUTES; do
  az storage blob upload -f dist-azure/index.html -c '$web' -n "$r" --account-name "$SA" --account-key "$KEY" --overwrite \
    --content-type "text/html" --content-cache-control "no-cache" -o none --only-show-errors
done
# Remove route copies that are no longer public pages (e.g. the old author workspace).
for b in $(az storage blob list -c '$web' --account-name "$SA" --account-key "$KEY" --query "[?!starts_with(name, 'assets/') && name != 'index.html'].name" -o tsv); do
  echo " $ROUTES " | tr '\n' ' ' | grep -q " $b " || az storage blob delete -c '$web' -n "$b" --account-name "$SA" --account-key "$KEY" -o none --only-show-errors
done
# Remove assets from earlier builds that the current index no longer references.
CURRENT=$(cd dist-azure && find assets -type f | sort)
for b in $(az storage blob list -c '$web' --prefix assets/ --account-name "$SA" --account-key "$KEY" --query "[].name" -o tsv); do
  echo "$CURRENT" | grep -qx "$b" || az storage blob delete -c '$web' -n "$b" --account-name "$SA" --account-key "$KEY" -o none --only-show-errors
done
echo "deployed: $(az storage account show -n "$SA" -g "$RG" --query primaryEndpoints.web -o tsv)"
