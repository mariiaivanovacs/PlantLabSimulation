"""
Load the persisted plant-knowledge vector index, or build it if missing.

Ensures vectorization is built once and cached on disk.
"""
import logging
from pathlib import Path
import os

from dotenv import load_dotenv
from llama_index.core import StorageContext, load_index_from_storage, VectorStoreIndex
from llama_index.core import SimpleDirectoryReader

# Load environment variables from .env file
load_dotenv(Path(__file__).resolve().parent / ".env")

# get openai api key from environment
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY", "")

# from .build_index import build_index, DEFAULT_KNOWLEDGE_DIR, DEFAULT_PERSIST_DIR

logger = logging.getLogger(__name__)

# Defaults (relative to project root)
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "index" / "plant_knowledge"
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "index" / "storage"


import os
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

_index = None  # global index

def load_or_build_index(
    knowledge_dir: str = DEFAULT_KNOWLEDGE_DIR,
    persist_dir: str = DEFAULT_PERSIST_DIR,
):
    """
    Load the vector index from *persist_dir* if it exists, 
    otherwise build it from documents in *knowledge_dir* and persist.
    
    Returns:
        A ready-to-query VectorStoreIndex.
    """
    global _index
    persist_dir = Path(persist_dir)

    if persist_dir.exists() and (persist_dir / "docstore.json").exists():
        logger.info(f"Loading cached index from {persist_dir}")
        print("Loading cached index from disk...")
        storage_context = StorageContext.from_defaults(persist_dir=str(persist_dir))
        _index = load_index_from_storage(storage_context)
        logger.info("Index loaded from cache")
    else:
        logger.info("No cached index found, building from knowledge documents ...")
        print("Building index from knowledge documents...")
        documents = SimpleDirectoryReader(str(knowledge_dir), filename_as_id=True).load_data()
        _index = VectorStoreIndex.from_documents(documents)
        os.makedirs(persist_dir, exist_ok=True)
        _index.storage_context.persist(persist_dir=str(persist_dir))
        logger.info(f"Index built and persisted at {persist_dir}")

    return _index



if __name__ == "__main__":
    load_or_build_index()
