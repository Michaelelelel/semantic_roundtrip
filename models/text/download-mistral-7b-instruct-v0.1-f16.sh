#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
revision='630f6d71b6a4d7f7a988e2a1a2049beee40dcca6'

download_file \
    "https://huggingface.co/ddh0/Mistral-7B-Instruct-v0.1-GGUF-fp16/resolve/${revision}/mistral-7B-instruct-v0.1-fp16.gguf?download=true" \
    "${model_root}/text/mistral-7b-instruct-v0.1-f16.gguf" \
    'd09ae9327489d49768e1e54506dde46e6ccccd00bf61fcfb4bf237ddbf4112fc'
