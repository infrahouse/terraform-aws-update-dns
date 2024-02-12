set -eux

mkdir -p "$TARGET_DIR"
pip install --target "$TARGET_DIR" -r "$REQUIREMENTS_FILE" --upgrade
find "$TARGET_DIR" -name __pycache__ -exec rm -rv {} +

#tar zcf - "$TARGET_DIR" | md5sum | cut -f 1 -d " " > "$MODULE_DIR/update_dns.md5"
