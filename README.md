# drop2blob

Python env setup:

Create a virtualenv in which the `drop2blob` command is available:

    ./pip_install_editable.sh

Typical usage:

    drop2blob \
      --blob-container-name YOUR_BLOB_CONTAINER \
      --connection-string YOUR_CONNECTION_STRING \
      --device YOUR_DEVICE_ID \
      --year 2024 \
      --month 05 \
      workflow


