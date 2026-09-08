# Sentinel Tool offline desktop release

The offline release is designed for the investigator workflow: open Sentinel Tool, sign in, upload CSV/JSON/XML evidence, and review the automatically generated results.

## One-time workstation preparation

The Linux workstation needs Docker Engine and the Docker Compose plugin. No internet connection is required when the release contains `sentinel-offline-images.tar`.

Verify the transferred package, then install the desktop entry:

```bash
sha256sum --check SHA256SUMS
bash ./scripts/install-desktop-launcher.sh
```

After that, open **Sentinel Tool** from the applications menu or desktop. The first start loads the bundled images, generates private local database credentials, starts MongoDB/API/worker services, waits for them to become healthy, and opens the sign-in page.

New investigators can create a local account from the sign-in screen. Accounts, cases, imported evidence, review state, and results persist in the local `sentinel-tool_mongo_data` Docker volume.

## Normal use

1. Open **Sentinel Tool**.
2. Sign in or create a local account.
3. Select **Import dataset** and choose a CSV, JSON, or XML file.
4. If the account has no case, Sentinel creates one for the file automatically.
5. Validation and analysis run automatically. Sentinel opens the ranked alert results when processing completes.

No package installation, model command, database command, or terminal is part of normal use.

## Stopping the local services

Run `bash ./scripts/stop-sentinel.sh`. Stopping services does not delete data. Never remove the `sentinel-tool_mongo_data` volume unless all local Sentinel data is intentionally being destroyed.

## Building a transferable release

Run this only on an internet-connected build machine:

```bash
bash ./scripts/package-offline.sh 0.2.0
```

Transfer the generated `dist-offline/Sentinel-Tool-0.2.0-linux-x86_64` directory to the offline workstation. Build on the same CPU architecture as the destination.
