#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
destination_directory="${model_root}/multimodal/gemma-3-27b-it-f16"
revision='f94c25afed0072339c5fa3b705a7b4222afe5f62'
repository="https://huggingface.co/ggml-org/gemma-3-27b-it-GGUF/resolve/${revision}"

download_file \
    "${repository}/gemma-3-27b-it-f16-00001-of-00002.gguf?download=true" \
    "${destination_directory}/gemma-3-27b-it-f16-00001-of-00002.gguf" \
    '6258f551a72788192d902be2c4cc23ab1c252ccb64a57eb5991a2bad1e499664'

download_file \
    "${repository}/gemma-3-27b-it-f16-00002-of-00002.gguf?download=true" \
    "${destination_directory}/gemma-3-27b-it-f16-00002-of-00002.gguf" \
    'd510a9a0deb28845a8de2424ca4383ccf8b3a14f71d92c158b315d77ac62a1ac'

download_file \
    "${repository}/mmproj-model-f16.gguf?download=true" \
    "${destination_directory}/mmproj-model-f16.gguf" \
    '54cb61c842fe49ac3c89bc1a614a2778163eb49f3dec2b90ff688b4c0392cb48'
