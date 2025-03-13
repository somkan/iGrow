import requests
import json
from datetime import datetime

class MongoDBConnection:
    def __init__(self, api_key, endpoints):
        self.api_key = api_key
        self.endpoints = endpoints
        self.headers = {
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def _handle_response(self, response):
        try:
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            print(f"MongoDB Error: {e}")
            print(f"Response: {response.text}")
            return None

    # Add this method to the MongoDBConnection class
    def find_one(self, collection, database, filter):
      endpoint = self.endpoints.get("find")
      if not endpoint:
        print("Find endpoint not configured")
        return None

      payload = {
        "collection": collection,
        "database": database,
        "dataSource": "Cluster0",
        "filter": filter
      }

      try:
        response = requests.post(
            endpoint,
            headers=self.headers,
            data=json.dumps(payload, default=self._json_serial)
        )
        return self._handle_response(response)
      except Exception as e:
        print(f"Find failed: {str(e)}")
        return None
    def find_many(self, collection, database, filter=None, sort=None, limit=None):
        """
        Perform a find operation on the MongoDB collection.
        
        :param collection: The name of the collection to query.
        :param database: The name of the database.
        :param filter: A dictionary specifying the query filter.
        :param sort: A dictionary specifying the sort order.
        :param limit: An integer specifying the maximum number of documents to return.
        :return: A list of documents matching the query.
        """
        url = self.endpoints["find_all"]
        payload = {
            "collection": collection,
            "database": database,
            "dataSource": "Cluster0",
        }

        if filter:
            payload["filter"] = filter
        if sort:
            payload["sort"] = sort
        if limit:
            payload["limit"] = limit

        try:
            response = requests.post(
            url ,
            headers=self.headers,
            data=json.dumps(payload, default=self._json_serial)
             )
            return self._handle_response(response)
        except Exception as e:
           print(f"Find failed: {str(e)}")
           return None
    def delete_many(self, collection, database, filter):
        endpoint = self.endpoints.get("delete_many")
        if not endpoint:
            print("Delete endpoint not configured")
            return None

        payload = {
            "collection": collection,
            "database": database,
            "dataSource": "Cluster0",
            "filter": filter
        }

        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                data=json.dumps(payload, default=self._json_serial))
            return self._handle_response(response)
        except Exception as e:
            print(f"Delete failed: {str(e)}")
            return None

    def insert_many(self, collection, database, documents):
        endpoint = self.endpoints.get("insert_all")
        if not endpoint:
            print("Insert endpoint not configured")
            return None

        payload = {
            "collection": collection,
            "database": database,
            "dataSource": "Cluster0",
            "documents": [self._sanitize_doc(doc) for doc in documents]
        }

        try:
            response = requests.post(
                endpoint,
                headers=self.headers,
                data=json.dumps(payload, default=self._json_serial))
            return self._handle_response(response)
        except Exception as e:
            print(f"Insert failed: {str(e)}")
            return None

     # Add to MongoDBConnection class
    def insert_one(self, collection, database, document):
       endpoint = self.endpoints.get("insert")
       if not endpoint:
         print("Insert endpoint not configured")
         return None

       payload = {
        "collection": collection,
        "database": database,
        "dataSource": "Cluster0",
        "document": self._sanitize_doc(document)
        }

       try:
        response = requests.post(
            endpoint,
            headers=self.headers,
            data=json.dumps(payload, default=self._json_serial))
        return self._handle_response(response)
       except Exception as e:
        print(f"Insert failed: {str(e)}")
        return None

    def update_one(self, collection, database, filter, update):
      endpoint = self.endpoints.get("update")
      if not endpoint:
        print("Update endpoint not configured")
        return None

      payload = {
     "collection": collection,
     "database": database,
     "dataSource": "Cluster0",
     "filter": filter,
     "update": update,  # Directly use the provided update document
     "upsert": False
      }
      try:
        response = requests.post(
            endpoint,
            headers=self.headers,
            data=json.dumps(payload, default=self._json_serial))
        return self._handle_response(response)
      except Exception as e:
         print(f"Insert failed: {str(e)}")
         return None
    
    def _json_serial(self, obj):
        """JSON serializer for objects not serializable by default"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        raise TypeError(f"Type {type(obj)} not serializable")


    # Add to MongoDBConnection class
    def get_refresh_token(self, user):
       response = self.find_one(
        "refresh_tokens", "myFirstDatabase", {"userid": user}
        )
       if response and "document" in response:
           return response["document"]["refresh_token"]
       raise ValueError(f"No refresh token found for user {user}")
    
    def _sanitize_doc(self, doc):
        """Convert _id to string if present"""
        if '_id' in doc:
            doc['_id'] = str(doc['_id'])
        return doc