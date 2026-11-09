import os, tempfile
os.environ.setdefault("SAAKSHI_DATA_DIR", tempfile.mkdtemp())
# tests never reach real services: no Kavach Shield, no harness key from a developer's .env
os.environ["KAVACH_SHIELD_URL"] = ""
os.environ["KAVACH_SHIELD_KEY"] = ""
os.environ["SAAKSHI_HARNESS_KEY"] = ""
