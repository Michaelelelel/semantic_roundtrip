#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

model_root="${1:-${script_directory}/..}"
diffusion_directory="${model_root}/image/diffusion_models"
encoder_directory="${model_root}/image/text_encoders"
vae_directory="${model_root}/image/vae"
repository='https://huggingface.co/Comfy-Org/Qwen-Image_ComfyUI/resolve/7beb7b647f04469fbe64ba8adc2bb0d7e5e9f73f'

download_file \
    "${repository}/split_files/diffusion_models/qwen_image_2512_bf16.safetensors?download=true" \
    "$diffusion_directory/qwen_image_2512_bf16.safetensors" \
    'cbf55390fff27dbc785046d7007b04e0c5dd7421e7ef128f2831eacb53a8e075'

download_file \
    "${repository}/split_files/text_encoders/qwen_2.5_vl_7b.safetensors?download=true" \
    "$encoder_directory/qwen_2.5_vl_7b.safetensors" \
    'cfafd739459bc86257397259f612a9aee88e5b98e85b5c0d0d1717e898b3463a'

download_file \
    "${repository}/split_files/vae/qwen_image_vae.safetensors?download=true" \
    "$vae_directory/qwen_image_vae.safetensors" \
    'a70580f0213e67967ee9c95f05bb400e8fb08307e017a924bf3441223e023d1f'
