#!/bin/sh
set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
model_root="${1:-$script_directory}"

# Native-precision text and multimodal models used by the main study.
"${script_directory}/text/download-mistral-7b-instruct-v0.1-f16.sh" "$model_root"
"${script_directory}/text/download-mistral-small-24b-instruct-2501-f16.sh" "$model_root"
"${script_directory}/text/download-qwen3-30b-a3b-instruct-2507-bf16.sh" "$model_root"
"${script_directory}/multimodal/download-qwen3.8-27b-bf16.sh" "$model_root"
"${script_directory}/multimodal/download-gemma-4-31b-it-bf16.sh" "$model_root"

# Native-precision vision models and the fixed verifier.
"${script_directory}/vision/download-llava-v1.5-7b-f16.sh" "$model_root"
"${script_directory}/vision/download-qwen2.5-vl-7b-instruct-f16.sh" "$model_root"

# Image generators used by the controlled image-model comparison.
"${script_directory}/image/download-stable-diffusion-v1-5-fp16.sh" "$model_root"
"${script_directory}/image/download-stable-diffusion-xl-base-1.0-fp16.sh" "$model_root"
"${script_directory}/image/download-stable-diffusion-3.5-large-bf16.sh" "$model_root"
"${script_directory}/image/download-qwen-image-2512-bf16.sh" "$model_root"
