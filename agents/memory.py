"""Reads/writes history from Firebase"""

class Memory:
    """Agent memory for storing and retrieving history"""
    
    def __init__(self, firebase_service=None):
        self.firebase_service = firebase_service
        self.local_cache = []
    
    def store(self, data):
        """Store data to memory"""
        self.local_cache.append(data)
        
        if self.firebase_service:
            # Store to Firebase
            self.firebase_service.write(data)
    
    def retrieve(self, query=None):
        """Retrieve data from memory"""
        if self.firebase_service:
            # Retrieve from Firebase
            return self.firebase_service.read(query)
        
        return self.local_cache
    
    def clear(self):
        """Clear memory"""
        self.local_cache = []

