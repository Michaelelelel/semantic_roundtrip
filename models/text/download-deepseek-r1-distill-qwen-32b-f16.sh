#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/text/deepseek-r1-distill-qwen-32b-f16"
revision='1938d05cc893a60f37be1dc16e7465038f4fca63'
repository="https://huggingface.co/unsloth/DeepSeek-R1-Distill-Qwen-32B-GGUF/resolve/${revision}/DeepSeek-R1-Distill-Qwen-32B-F16"

download_file \
    "${repository}/DeepSeek-R1-Distill-Qwen-32B-F16-00001-of-00002.gguf?download=true" \
    "${destination_directory}/DeepSeek-R1-Distill-Qwen-32B-F16-00001-of-00002.gguf" \
    '70e044a411dacdd7fe24344a37ae8f49d6e8f24044137da3313d2fe9058ef0e5'

download_file \
    "${repository}/DeepSeek-R1-Distill-Qwen-32B-F16-00002-of-00002.gguf?download=true" \
    "${destination_directory}/DeepSeek-R1-Distill-Qwen-32B-F16-00002-of-00002.gguf" \
    'a0fa8a8019219c88a1dd9b58dbd89ae4091173eb4af7739bc281757315e492ee'
