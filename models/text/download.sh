#!/bin/sh
set -eu

model_root="${1:-$(dirname "$0")/..}"
mkdir -p "${model_root}/text"
curl -fL 'https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.1-GGUF/resolve/731a9fc8f06f5f5e2db8a0cf9d256197eb6e05d1/mistral-7b-instruct-v0.1.Q4_K_M.gguf?download=true' -o "${model_root}/text/mistral-7b-instruct-v0.1.Q4_K_M.gguf"
