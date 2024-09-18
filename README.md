# drop2blob

Just like the `drop2s3` CLI tool (see https://github.com/billagee/dropbox-to-s3) but with an Azure blob container as the backup target, not S3.

Installation:

Create a virtualenv and install the `drop2blob` package in it:

    ./pip_install_editable.sh

Activate the venv in your shell:

    source env/bin/activate

Then make sure you've authenticated with `az login`.

Usage:

    drop2blob \
      --blob-container-name YOUR_BLOB_CONTAINER \
      --connection-string YOUR_CONNECTION_STRING \
      --device YOUR_DEVICE_ID \
      --year 2024 \
      --month 05 \
      workflow


