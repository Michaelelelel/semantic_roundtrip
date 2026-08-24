#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/text/qwen3-30b-a3b-instruct-2507"
revision='eea7b2be5805a5f151f8847ede8e5f9a9284bf77'
repository="https://huggingface.co/unsloth/Qwen3-30B-A3B-Instruct-2507-GGUF/resolve/${revision}/BF16"

download_file \
    "${repository}/Qwen3-30B-A3B-Instruct-2507-BF16-00001-of-00002.gguf?download=true" \
    "${destination_directory}/Qwen3-30B-A3B-Instruct-2507-BF16-00001-of-00002.gguf" \
    'c5f340800a4d94717d45b2c6c4a89ddd741f0df8c3deeef49bf551374fd3e3ff'

download_file \
    "${repository}/Qwen3-30B-A3B-Instruct-2507-BF16-00002-of-00002.gguf?download=true" \
    "${destination_directory}/Qwen3-30B-A3B-Instruct-2507-BF16-00002-of-00002.gguf" \
    '8ed5fbc766a3a626279592fb36c093179d89126931af0b05751b61504475e287'
