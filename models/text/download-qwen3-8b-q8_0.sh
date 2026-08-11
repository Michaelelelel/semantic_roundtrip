#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
destination_directory="${model_root}/text/qwen3-8b"
mkdir -p "$destination_directory"

destination="${destination_directory}/Qwen3-8B-Q8_0.gguf"
temporary="${destination}.part"
checksum="408b955510e196121c1c375201744783b5c9a43c7956d73fc78df54c66e883d6"

if [ -f "$destination" ] && printf '%s  %s\n' "$checksum" "$destination" | sha256sum --check --status; then
    echo "Already downloaded: $destination"
    exit 0
fi

curl -fL --retry 3 --continue-at - \
    'https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/7c41481f57cb95916b40956ab2f0b139b296d974/Qwen3-8B-Q8_0.gguf?download=true' \
    -o "$temporary"
printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
mv "$temporary" "$destination"
