#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"

download_file \
    'https://huggingface.co/Qwen/Qwen3-8B-GGUF/resolve/7c41481f57cb95916b40956ab2f0b139b296d974/Qwen3-8B-Q8_0.gguf?download=true' \
    "${model_root}/text/qwen3-8b/Qwen3-8B-Q8_0.gguf" \
    '408b955510e196121c1c375201744783b5c9a43c7956d73fc78df54c66e883d6'
