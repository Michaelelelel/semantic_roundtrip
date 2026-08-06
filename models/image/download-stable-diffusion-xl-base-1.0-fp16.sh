#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
mkdir -p "${model_root}/image/checkpoints"

destination="${model_root}/image/checkpoints/sd_xl_base_1.0.safetensors"
temporary="${destination}.part"
checksum="31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b"

if [ -f "$destination" ] && printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
    echo "Already downloaded: $destination"
    exit 0
fi

curl -fL --retry 3 --continue-at - \
    'https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/47cd5302d866fa60cf8fb81f0e34d42e38f6100c/sd_xl_base_1.0.safetensors?download=true' \
    -o "$temporary"
printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
mv "$temporary" "$destination"
