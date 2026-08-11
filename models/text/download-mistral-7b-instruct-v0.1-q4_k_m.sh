#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
destination_directory="${model_root}/text"
mkdir -p "$destination_directory"

destination="${destination_directory}/mistral-7b-instruct-v0.1.Q4_K_M.gguf"
temporary="${destination}.part"
checksum="14466f9d658bf4a79f96c3f3f22759707c291cac4e62fea625e80c7d32169991"

if [ -f "$destination" ] && printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
    echo "Already downloaded: $destination"
    exit 0
fi

curl -fL --retry 3 --continue-at - \
    'https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/731a9fc8f06f5f5e2db8a0cf9d256197eb6e05d1/mistral-7b-instruct-v0.1.Q4_K_M.gguf?download=true' \
    -o "$temporary"
printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
mv "$temporary" "$destination"
