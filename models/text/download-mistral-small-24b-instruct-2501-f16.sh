#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
revision='62a613c92d5a5f73bba6d348b51433b232c4640c'

download_file \
    "https://huggingface.co/bartowski/Mistral-Small-24B-Instruct-2501-GGUF/resolve/${revision}/Mistral-Small-24B-Instruct-2501-f16.gguf?download=true" \
    "${model_root}/text/mistral-small-24b-instruct-2501-f16.gguf" \
    'c5d082bbeae78ee960f4637c170e553bae85895390bc3326b45de6d62523b62c'
