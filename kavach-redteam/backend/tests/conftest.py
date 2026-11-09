import os, tempfile
# tests use a throwaway database and never reach real services, whatever a developer's .env says
os.environ["KAVACH_DATA_DIR"] = tempfile.mkdtemp()
os.environ["SAAKSHI_HARNESS_KEY"] = ""
os.environ["KAVACH_ADMIN_KEY"] = ""
os.environ["KAVACH_ENV"] = "development"
