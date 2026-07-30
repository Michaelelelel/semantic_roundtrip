#!/bin/sh
set -eu

curl -fsSL 'https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1/resolve/b422f01f8a0eba935d8f7fbc436dc5d1ab25a250/tokenizer_config.json' | jq -er '.chat_template' > "$(dirname "$0")/mistral-7b-instruct-v0.1.jinja"

curl -fsSL 'https://huggingface.co/llava-hf/llava-1.5-7b-hf/resolve/b234b804b114d9e37bb655e11cbbb5f5e971b7a9/chat_template.jinja' > "$(dirname "$0")/llava-v1.5.jinja"
