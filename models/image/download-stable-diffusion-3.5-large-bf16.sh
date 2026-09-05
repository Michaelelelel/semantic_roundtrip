#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
. "${script_directory}/../download-helper.sh"

require_hf_token \
    'the gated Stable Diffusion 3.5 Large checkpoint' \
    'https://huggingface.co/stabilityai/stable-diffusion-3.5-large'

model_root="${1:-${script_directory}/..}"
checkpoint_directory="${model_root}/image/checkpoints"
encoder_directory="${model_root}/image/text_encoders"

download_file \
    'https://huggingface.co/stabilityai/stable-diffusion-3.5-large/resolve/ceddf0a7fdf2064ea28e2213e3b84e4afa170a0f/sd3.5_large.safetensors?download=true' \
    "$checkpoint_directory/sd3.5_large.safetensors" \
    'ffef7a279d9134626e6ce0d494fba84fc1c7e720b3c7df2d19a09dc3796d8f93' \
    "$HF_TOKEN"

encoder_revision='05a7e90d80ab0eb9bcc2fa198a08273a133ec56c'
encoder_base_url="https://huggingface.co/Comfy-Org/stable-diffusion-3.5-fp8/resolve/${encoder_revision}/text_encoders"

download_file \
    "$encoder_base_url/clip_l.safetensors?download=true" \
    "$encoder_directory/clip_l.safetensors" \
    '660c6f5b1abae9dc498ac2d21e1347d2abdb0cf6c0c0c8576cd796491d9a6cdd'

download_file \
    "$encoder_base_url/clip_g.safetensors?download=true" \
    "$encoder_directory/clip_g.safetensors" \
    'ec310df2af79c318e24d20511b601a591ca8cd4f1fce1d8dff822a356bcdb1f4'

download_file \
    "$encoder_base_url/t5xxl_fp16.safetensors?download=true" \
    "$encoder_directory/t5xxl_fp16.safetensors" \
    '6e480b09fae049a72d2a8c5fbccb8d3e92febeb233bbe9dfe7256958a9167635'
