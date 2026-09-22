#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
model_root="${1:-$script_directory}"

# Text and multimodal models used by the final study.
sh "${script_directory}/text/download-gpt-oss-120b-mxfp4.sh" "$model_root"
sh "${script_directory}/text/download-deepseek-r1-distill-qwen-32b-f16.sh" "$model_root"
sh "${script_directory}/multimodal/download-qwen2.5-vl-32b-instruct-f16.sh" "$model_root"
sh "${script_directory}/multimodal/download-gemma-3-27b-it-f16.sh" "$model_root"
sh "${script_directory}/multimodal/download-qwen3.8-27b-bf16.sh" "$model_root"
sh "${script_directory}/multimodal/download-gemma-4-31b-it-bf16.sh" "$model_root"

# Verification reuses the Qwen3.8 multimodal checkpoint downloaded above.

# Fixed image generator.
sh "${script_directory}/image/download-stable-diffusion-3.5-large-bf16.sh" "$model_root"
