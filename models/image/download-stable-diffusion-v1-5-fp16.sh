#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
mkdir -p "${model_root}/image/checkpoints"

destination="${model_root}/image/checkpoints/v1-5-pruned-emaonly.safetensors"
temporary="${destination}.part"
checksum="6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa"

if [ -f "$destination" ] && printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
    echo "Already downloaded: $destination"
    exit 0
fi

curl -fL --retry 3 --continue-at - \
    'https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors?download=true' \
    -o "$temporary"
printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
mv "$temporary" "$destination"
