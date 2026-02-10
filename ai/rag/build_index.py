"""
Build the plant-knowledge vector index from markdown documents.

Reads all .md files from the knowledge directory, chunks them,
embeds via OpenAI, and persists the VectorStoreIndex to disk.
"""
import logging
from pathlib import Path

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, StorageContext

logger = logging.getLogger(__name__)

# Defaults (relative to project root)
DEFAULT_KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "index" / "plant_knowledge"
DEFAULT_PERSIST_DIR = Path(__file__).resolve().parent.parent / "index" / "storage"


def build_index(
    knowledge_dir: Path = DEFAULT_KNOWLEDGE_DIR,
    persist_dir: Path = DEFAULT_PERSIST_DIR,
) -> VectorStoreIndex:
    """
    Build a VectorStoreIndex from all .md files in *knowledge_dir*
    and persist it to *persist_dir*.

    Uses the default OpenAI embedding model (text-embedding-3-small).

    Returns:
        The built VectorStoreIndex.
    """
    knowledge_dir = Path(knowledge_dir)
    persist_dir = Path(persist_dir)

    if not knowledge_dir.exists() or not any(knowledge_dir.glob("*.md")):
        raise FileNotFoundError(
            f"No .md files found in {knowledge_dir}. "
            "Add plant-domain documents before building the index."
        )

    logger.info(f"Building index from {knowledge_dir} ...")
    documents = SimpleDirectoryReader(
        input_dir=str(knowledge_dir),
        required_exts=[".md"],
    ).load_data()
    logger.info(f"Loaded {len(documents)} document(s)")

    index = VectorStoreIndex.from_documents(documents)

    # Persist to disk
    persist_dir.mkdir(parents=True, exist_ok=True)
    index.storage_context.persist(persist_dir=str(persist_dir))
    logger.info(f"Index persisted to {persist_dir}")

    return index
