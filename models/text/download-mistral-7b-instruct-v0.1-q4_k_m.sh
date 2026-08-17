#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"

download_file \
    'https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/731a9fc8f06f5f5e2db8a0cf9d256197eb6e05d1/mistral-7b-instruct-v0.1.Q4_K_M.gguf?download=true' \
    "${model_root}/text/mistral-7b-instruct-v0.1.Q4_K_M.gguf" \
    '14466f9d658bf4a79f96c3f3f22759707c291cac4e62fea625e80c7d32169991'
