#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"

download_file \
    'https://huggingface.co/ggml-org/gpt-oss-120b-GGUF/resolve/238abdd290bb874b90a5da1b4549881b7d05c091/gpt-oss-120b-MXFP4.gguf?download=true' \
    "${model_root}/text/gpt-oss-120b/gpt-oss-120b-MXFP4.gguf" \
    '582bd40f6886200101f4c4ed9f25f3fe80cc14c86e9e2b37746cd8904a0c622d'
