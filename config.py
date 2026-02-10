# Paths
import os
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


MD_FILES_DIR = os.path.join(BASE_DIR, "..", "..", "md_files")
GENERATED_DOCS_DIR = os.path.join(BASE_DIR, "..", "instance", "generated_docs")
TEMPLATE_DIR = os.path.join(BASE_DIR, "..", "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "..", "instance", "generated_docs")
INDEX_STORE_DIR = os.path.join(BASE_DIR, "..", "instance", "index_store")