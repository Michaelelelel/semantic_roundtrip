#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"

download_file \
    'https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors?download=true' \
    "${model_root}/image/checkpoints/v1-5-pruned-emaonly.safetensors" \
    '6ce0161689b3853acaa03779ec93eafe75a02f4ced659bee03f50797806fa2fa'
