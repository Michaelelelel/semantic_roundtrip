#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
model_root="${1:-$script_directory}"

"${script_directory}/download-dgx-initial-stack-smoke.sh" "$model_root"

"${script_directory}/image/download-stable-diffusion-3.5-large-bf16.sh" "$model_root"
"${script_directory}/multimodal/download-qwen3.6-27b-q8_0.sh" "$model_root"
"${script_directory}/vision/download-gemma-4-31b-it-q8_0.sh" "$model_root"

"${script_directory}/text/download-gpt-oss-120b-mxfp4.sh" "$model_root"
"${script_directory}/image/download-qwen-image-2512-bf16.sh" "$model_root"

"${script_directory}/multimodal/download-mistral-small-4-119b-q4_k_m.sh" "$model_root"
"${script_directory}/image/download-flux2-dev-fp8mixed.sh" "$model_root"
