# Shared download functions for the model scripts.

# Usage: download_file URL DESTINATION SHA256 [HF_TOKEN]
download_file() (
    url="$1"
    destination="$2"
    checksum="$3"
    token="${4:-}"
    temporary="${destination}.part"

    mkdir -p "$(dirname -- "$destination")"

    if [ -f "$destination" ] &&
        printf '%s  %s\n' "$checksum" "$destination" |
            sha256sum --check --status; then
        echo "Already downloaded: $destination"
        return
    fi

    if [ -f "$temporary" ] &&
        printf '%s  %s\n' "$checksum" "$temporary" |
            sha256sum --check --status; then
        mv "$temporary" "$destination"
        echo "Completed previous download: $destination"
        return
    fi

    if [ -n "$token" ]; then
        curl -fL --retry 3 --continue-at - \
            -H "Authorization: Bearer $token" \
            "$url" \
            -o "$temporary"
    else
        curl -fL --retry 3 --continue-at - \
            "$url" \
            -o "$temporary"
    fi

    printf '%s  %s\n' "$checksum" "$temporary" | sha256sum --check
    mv "$temporary" "$destination"
)

# Stop early with a useful message when a gated model needs authentication.
require_hf_token() {
    if [ -z "${HF_TOKEN:-}" ]; then
        echo "HF_TOKEN is required for $1." >&2
        echo "Accept the license first: $2" >&2
        exit 1
    fi
}
