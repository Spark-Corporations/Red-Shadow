"""
MemoryRAG — Vector database for CVE lookup, past exploits, and 0day archive.

Uses ChromaDB as the vector store with 3 collections:
  1. cve_database: NVD CVE data (200K+ entries)
  2. past_exploits: Successful exploit history (learning loop)
  3. zeroday_archive: Proprietary findings (internal only)

Falls back to in-memory storage if ChromaDB is not available.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("redclaw.memory.memory_rag")

# Try to import ChromaDB, fall back to in-memory implementation
try:
    import chromadb
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    logger.warning("ChromaDB not installed. Using in-memory fallback. Install with: pip install chromadb")


# ── In-Memory Fallback ───────────────────────────────────────────────────────


class InMemoryCollection:
    """Simple in-memory collection when ChromaDB is not available."""

    def __init__(self, name: str):
        self.name = name
        self._documents: list[dict] = []

    def add(self, documents: list[str], metadatas: list[dict], ids: list[str]):
        for doc, meta, id_ in zip(documents, metadatas, ids):
            self._documents.append({"id": id_, "document": doc, "metadata": meta})

    def query(self, query_texts: list[str], n_results: int = 5) -> dict:
        """Simple keyword match fallback."""
        query_lower = query_texts[0].lower() if query_texts else ""
        matches = []
        for doc in self._documents:
            if query_lower in doc["document"].lower():
                matches.append(doc)
        matches = matches[:n_results]
        return {
            "documents": [[d["document"] for d in matches]],
            "metadatas": [[d["metadata"] for d in matches]],
            "ids": [[d["id"] for d in matches]],
        }

    def get(self) -> dict:
        return {
            "documents": [d["document"] for d in self._documents],
            "metadatas": [d["metadata"] for d in self._documents],
            "ids": [d["id"] for d in self._documents],
        }

    def count(self) -> int:
        return len(self._documents)


class InMemoryClient:
    """Simple in-memory client when ChromaDB is not available."""

    def __init__(self):
        self._collections: dict[str, InMemoryCollection] = {}

    def get_or_create_collection(self, name: str) -> InMemoryCollection:
        if name not in self._collections:
            self._collections[name] = InMemoryCollection(name)
        return self._collections[name]


# ── Memory RAG ────────────────────────────────────────────────────────────────


class MemoryRAG:
    """
    Vector database for CVE lookup, exploit history, and 0day storage.

    Usage:
        rag = MemoryRAG()

        # Query CVE database
        cves = await rag.query_cve("Apache", "2.4.49")

        # Check past exploits
        past = await rag.query_past_exploits("Apache", "2.4.49")

        # Store successful exploit (learning loop)
        await rag.store_successful_exploit(exploit_data)
    """

    def __init__(self, persist_directory: Optional[str] = None):
        if persist_directory is None:
            persist_directory = os.path.join(os.path.expanduser("~/.redclaw"), "chromadb")

        if HAS_CHROMADB:
            os.makedirs(persist_directory, exist_ok=True)
            self.client = chromadb.PersistentClient(path=persist_directory)
            logger.info(f"MemoryRAG initialized with ChromaDB at {persist_directory}")
        else:
            self.client = InMemoryClient()
            logger.info("MemoryRAG initialized with in-memory fallback")

        # Collections
        self.cve_collection = self.client.get_or_create_collection("cve_database")
        self.exploit_collection = self.client.get_or_create_collection("past_exploits")
        self.zeroday_collection = self.client.get_or_create_collection("zeroday_archive")

    # ── CVE Database ──────────────────────────────────────────────────────

    async def query_cve(self, service: str, version: str, n_results: int = 5) -> List[Dict]:
        """
        Query CVE database for a given service and version.

        Returns list of matching CVEs sorted by relevance.
        """
        query = f"{service} {version} vulnerability"

        results = self.cve_collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        cves = []
        if results["metadatas"] and results["metadatas"][0]:
            for i, meta in enumerate(results["metadatas"][0]):
                cves.append({
                    "cve": meta.get("cve_id", ""),
                    "description": results["documents"][0][i] if results["documents"][0] else "",
                    "cvss": meta.get("cvss_score", 0),
                    "published": meta.get("published_date", ""),
                })

        logger.debug(f"CVE query '{service} {version}': {len(cves)} results")
        return cves

    async def ingest_cve(self, cve_id: str, description: str, cvss_score: float = 0,
                          published_date: str = "", affected_products: str = ""):
        """Add a single CVE to the database."""
        self.cve_collection.add(
            documents=[description],
            metadatas=[{
                "cve_id": cve_id,
                "cvss_score": cvss_score,
                "published_date": published_date,
                "affected_products": affected_products,
            }],
            ids=[cve_id],
        )

    # ── Past Exploits ─────────────────────────────────────────────────────

    async def query_past_exploits(self, service: str, version: str, n_results: int = 3) -> List[Dict]:
        """
        Find similar past successful exploits.

        Returns exploits that worked on similar services/versions.
        """
        query = f"{service} {version}"

        results = self.exploit_collection.query(
            query_texts=[query],
            n_results=n_results,
        )

        exploits = []
        if results["documents"] and results["documents"][0]:
            for i, doc in enumerate(results["documents"][0]):
                try:
                    exploit_data = json.loads(doc)
                except (json.JSONDecodeError, TypeError):
                    exploit_data = {"raw": doc}

                meta = results["metadatas"][0][i] if results["metadatas"][0] else {}
                exploits.append({
                    "target": exploit_data.get("target", ""),
                    "exploit_code": exploit_data.get("exploit_code", ""),
                    "success_rate": meta.get("success_rate", 0),
                    "notes": exploit_data.get("notes", ""),
                })

        logger.debug(f"Past exploit query '{service} {version}': {len(exploits)} results")
        return exploits

    async def store_successful_exploit(self, exploit_data: Dict[str, Any]):
        """
        Store a successful exploit for future reference (learning loop).
        """
        self.exploit_collection.add(
            documents=[json.dumps(exploit_data)],
            metadatas=[{
                "service": exploit_data.get("service", ""),
                "version": exploit_data.get("version", ""),
                "cve": exploit_data.get("cve", ""),
                "success_rate": 1.0,
                "timestamp": datetime.now().isoformat(),
            }],
            ids=[f"exploit_{uuid.uuid4().hex[:12]}"],
        )
        logger.info(f"Stored successful exploit: {exploit_data.get('service')} {exploit_data.get('version')}")

    # ── Zero-Day Archive ──────────────────────────────────────────────────

    async def store_zeroday(self, zeroday_data: Dict[str, Any]):
        """Store a proprietary zero-day finding."""
        self.zeroday_collection.add(
            documents=[json.dumps(zeroday_data)],
            metadatas=[{
                "binary": zeroday_data.get("binary", ""),
                "vulnerability_type": zeroday_data.get("type", ""),
                "severity": zeroday_data.get("severity", "unknown"),
                "discovered_date": datetime.now().isoformat(),
            }],
            ids=[f"zeroday_{uuid.uuid4().hex[:12]}"],
        )
        logger.info(f"Stored 0day: {zeroday_data.get('binary')} ({zeroday_data.get('type')})")

    async def query_zerodays(self, binary: str, n_results: int = 3) -> List[Dict]:
        """Query zero-day archive for a binary."""
        results = self.zeroday_collection.query(
            query_texts=[binary],
            n_results=n_results,
        )

        zerodays = []
        if results["documents"] and results["documents"][0]:
            for doc in results["documents"][0]:
                try:
                    zerodays.append(json.loads(doc))
                except (json.JSONDecodeError, TypeError):
                    pass

        return zerodays

    # ── General Query ─────────────────────────────────────────────────────

    async def query_relevant_info(self, task_description: str) -> Dict[str, Any]:
        """
        Query all collections for info relevant to a task description.
        Used by teammates to enrich their context.
        """
        # Extract service/version from description
        parts = task_description.split()
        service = parts[0] if parts else ""
        version = parts[1] if len(parts) > 1 else ""

        cves = await self.query_cve(service, version, n_results=3)
        past_exploits = await self.query_past_exploits(service, version, n_results=2)

        return {
            "cves": cves,
            "past_exploits": past_exploits,
            "query": task_description,
        }

    # ── Stats ─────────────────────────────────────────────────────────────

    def get_stats(self) -> Dict[str, int]:
        """Get collection sizes."""
        return {
            "cve_count": self.cve_collection.count(),
            "exploit_count": self.exploit_collection.count(),
            "zeroday_count": self.zeroday_collection.count(),
        }
