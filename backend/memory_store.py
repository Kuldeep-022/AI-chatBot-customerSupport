"""
In-memory storage fallback for when MongoDB is not available.
This allows the application to run without requiring a database connection.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime


class InMemoryStore:
    """Simple in-memory storage that mimics MongoDB's async interface"""
    
    def __init__(self):
        self.collections = {}
    
    def __getitem__(self, collection_name: str):
        if collection_name not in self.collections:
            self.collections[collection_name] = InMemoryCollection(collection_name)
        return self.collections[collection_name]
    
    def __getattr__(self, collection_name: str):
        """Allow attribute-style access like db.faqs"""
        if collection_name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{collection_name}'")
        return self[collection_name]


class InMemoryCollection:
    """Mimics MongoDB collection with async methods"""
    
    def __init__(self, name: str):
        self.name = name
        self.documents = []
    
    async def find_one(self, query: Dict, projection: Optional[Dict] = None):
        """Find a single document matching the query"""
        for doc in self.documents:
            if self._matches_query(doc, query):
                return self._apply_projection(doc, projection)
        return None
    
    def find(self, query: Dict = None, projection: Optional[Dict] = None):
        """Find documents matching the query (returns async cursor)"""
        if query is None:
            query = {}
        return InMemoryCursor(self.documents, query, projection)
    
    async def insert_one(self, document: Dict):
        """Insert a single document"""
        self.documents.append(document.copy())
        return type('InsertResult', (), {'inserted_id': document.get('id', document.get('_id'))})()
    
    async def update_one(self, query: Dict, update: Dict):
        """Update a single document"""
        for i, doc in enumerate(self.documents):
            if self._matches_query(doc, query):
                if '$set' in update:
                    doc.update(update['$set'])
                else:
                    doc.update(update)
                return type('UpdateResult', (), {'modified_count': 1})()
        return type('UpdateResult', (), {'modified_count': 0})()
    
    async def delete_one(self, query: Dict):
        """Delete a single document"""
        for i, doc in enumerate(self.documents):
            if self._matches_query(doc, query):
                self.documents.pop(i)
                return type('DeleteResult', (), {'deleted_count': 1})()
        return type('DeleteResult', (), {'deleted_count': 0})()
    
    async def delete_many(self, query: Dict):
        """Delete multiple documents"""
        count = 0
        i = 0
        while i < len(self.documents):
            if self._matches_query(self.documents[i], query):
                self.documents.pop(i)
                count += 1
            else:
                i += 1
        return type('DeleteResult', (), {'deleted_count': count})()
    
    async def count_documents(self, query: Dict):
        """Count documents matching the query"""
        count = 0
        for doc in self.documents:
            if self._matches_query(doc, query):
                count += 1
        return count
    
    def _matches_query(self, document: Dict, query: Dict) -> bool:
        """Check if document matches the query"""
        if not query:
            return True
        for key, value in query.items():
            if key not in document or document[key] != value:
                return False
        return True
    
    def _apply_projection(self, document: Dict, projection: Optional[Dict]) -> Dict:
        """Apply projection to document"""
        if not projection:
            return document.copy()
        
        result = {}
        for key, value in projection.items():
            if value == 1 and key in document:
                result[key] = document[key]
            elif value == 0 and key not in projection:
                result = {k: v for k, v in document.items() if k != key}
        return result


class InMemoryCursor:
    """Mimics MongoDB cursor"""
    
    def __init__(self, documents: List[Dict], query: Dict, projection: Optional[Dict]):
        self.documents = documents
        self.query = query
        self.projection = projection
        self._sort_field = None
        self._sort_direction = 1
    
    def sort(self, field: str, direction: int = 1):
        """Sort the cursor results"""
        self._sort_field = field
        self._sort_direction = direction
        return self
    
    async def to_list(self, length: int = None) -> List[Dict]:
        """Convert cursor to list"""
        results = []
        for doc in self.documents:
            if self._matches_query(doc, self.query):
                results.append(self._apply_projection(doc, self.projection))
        
        # Apply sorting if specified
        if self._sort_field:
            results.sort(
                key=lambda x: x.get(self._sort_field, ''),
                reverse=(self._sort_direction == -1)
            )
        
        if length is not None:
            return results[:length]
        return results
    
    def _matches_query(self, document: Dict, query: Dict) -> bool:
        """Check if document matches the query"""
        if not query:
            return True
        for key, value in query.items():
            if key not in document or document[key] != value:
                return False
        return True
    
    def _apply_projection(self, document: Dict, projection: Optional[Dict]) -> Dict:
        """Apply projection to document"""
        if not projection:
            return document.copy()
        
        result = {}
        for key, value in projection.items():
            if value == 1 and key in document:
                result[key] = document[key]
            elif value == 0:
                result = {k: v for k, v in document.items() if k != key}
        return result
