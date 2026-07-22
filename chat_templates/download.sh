#!/bin/sh
curl -fsSL 'https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.1/resolve/b422f01f8a0eba935d8f7fbc436dc5d1ab25a250/tokenizer_config.json' | jq -er '.chat_template' > "$(dirname "$0")/mistral-7b-instruct-v0.1.jinja"
