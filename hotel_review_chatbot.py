#!/usr/bin/env python3
"""
Hotel Review Vector Search Chatbot

This application demonstrates the use of Couchbase's vector search capabilities
to build a simple chatbot that finds relevant hotel reviews based on user queries.
It uses semantic similarity via embeddings to match natural language queries
with review content.

Author: Your Name
License: MIT
"""

# Import required libraries
from sentence_transformers import SentenceTransformer
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions
from couchbase.auth import PasswordAuthenticator
from couchbase.exceptions import CouchbaseException
import couchbase.search as search
from couchbase.options import SearchOptions, ClusterTimeoutOptions
from couchbase.vector_search import VectorQuery, VectorSearch
import os
import sys
import json
from datetime import timedelta
import traceback

# Print SDK version for debugging
import couchbase
print(f"Couchbase Python SDK Version: {couchbase.__version__}")

# Load the sentence transformer model - use the same model as the embedding creation
model = SentenceTransformer('all-MiniLM-L6-v2')

# Couchbase Capella connection parameters
# Update these with your actual Capella connection details
CB_USERNAME = "Administrator"
CB_PASSWORD = "Password1!"
CB_HOSTNAME = "cb.0pjzyc2efdadlu6.cloud.couchbase.com"
CB_BUCKET = "travel-sample"
CB_SCOPE = "inventory"
CB_COLLECTION_TARGET = "reviewvector"
# Vector search index name
VECTOR_INDEX_NAME = "review_vector_idx"

# Path to the Capella certificate file
CERT_PATH = "/path/to/certificate.pem"  # Update this path

def connect_to_capella():
    """
    Establishes a connection to Couchbase Capella cluster.
    
    Returns:
        Cluster: A connected Couchbase cluster object or None if connection fails
    """
    print(f"Connecting to Couchbase Capella at {CB_HOSTNAME}...")
    try:
        # For Capella, we must use secure connections
        connection_string = f"couchbases://{CB_HOSTNAME}"
        
        # Set up authenticator with your Capella credentials
        auth = PasswordAuthenticator(CB_USERNAME, CB_PASSWORD)
        
        # Configure timeout options
        timeout_opts = ClusterTimeoutOptions(
            kv_timeout=timedelta(seconds=30),
            query_timeout=timedelta(seconds=75)
        )
        
        # Create cluster options with certificate path
        options = ClusterOptions(auth, timeout_options=timeout_opts)
        
        # Set certificate path for TLS/SSL connections
        options.ssl_cert = CERT_PATH
        
        # Connect to the cluster
        cluster = Cluster(connection_string, options)
        
        # Test connection
        ping_result = cluster.ping()
        print("Successfully connected to Couchbase Capella")
        print(f"Ping result: {ping_result}")
        return cluster
    except Exception as e:
        print(f"Connection error: {e}")
        print("\nTroubleshooting steps:")
        print("1. Verify your Capella username and password are correct")
        print("2. Check that your Capella endpoint URL is correct")
        print("3. Ensure your certificate file is valid and in the correct location")
        print("4. Check that your IP address is allowed in Capella's allowed IP list")
        traceback.print_exc()
        return None

def check_vector_search_index(cluster):
    """
    Checks if the required vector search index exists in the cluster.
    
    Args:
        cluster (Cluster): Connected Couchbase cluster
        
    Returns:
        bool: True if the index exists, False otherwise
    """
    try:
        # Make sure cluster is not None
        if cluster is None:
            print("Error: cluster object is None")
            return False
            
        # Check if vector search index already exists using a safer approach
        try:
            # Try to get indexes using the Search API if available
            mgr = cluster.search_indexes()
            indexes = mgr.get_all_indexes()
            index_exists = any(idx.name == VECTOR_INDEX_NAME for idx in indexes)
        except Exception as se:
            print(f"Search API not available, falling back to N1QL: {se}")
            # Fallback to N1QL query
            query = f"""
            SELECT name 
            FROM system:indexes 
            WHERE keyspace_id = '{CB_BUCKET}' 
              AND scope_id = '{CB_SCOPE}' 
              AND bucket_id = '{CB_BUCKET}'
              AND name = '{VECTOR_INDEX_NAME}'
            """
            result = list(cluster.query(query))
            index_exists = len(result) > 0
        
        if not index_exists:
            print(f"\nWARNING: Vector search index '{VECTOR_INDEX_NAME}' not found.")
            print("To use vector search, you need to create a Search index with vector capabilities.")
            print("You can create this through the Couchbase Web Console:")
            print(f"1. Go to Search → Add Index")
            print(f"2. Name the index '{VECTOR_INDEX_NAME}'")
            print(f"3. Select bucket '{CB_BUCKET}', scope '{CB_SCOPE}', collection '{CB_COLLECTION_TARGET}'")
            print(f"4. Add a vector mapping for the 'embedding' field with 384 dimensions")
            print(f"5. Save and build the index\n")
            return False
        else:
            print(f"Vector search index '{VECTOR_INDEX_NAME}' found.")
            return True
            
    except Exception as e:
        print(f"Error checking vector search index: {e}")
        traceback.print_exc()
        return False

def fallback_to_n1ql(cluster, query_embedding, top_k=5):
    """
    Performs vector search using N1QL with vector functions as a fallback method.
    
    Args:
        cluster (Cluster): Connected Couchbase cluster
        query_embedding (list): Vector embedding of the user query
        top_k (int): Number of results to return
        
    Returns:
        list: List of search results with similarity scores
    """
    print("Using N1QL query with vector functions as fallback")
    try:
        # Use a N1QL query with vector functions which works across SDK versions
        vector_query = f"""
        SELECT meta().id as doc_id, hotel_name, review_content, review_author, review_date, review_ratings,
               VECTOR_DISTANCE(embedding, $query_vector) AS distance_score
        FROM `{CB_BUCKET}`.`{CB_SCOPE}`.`{CB_COLLECTION_TARGET}`
        WHERE embedding IS NOT NULL
        ORDER BY VECTOR_DISTANCE(embedding, $query_vector)
        LIMIT {top_k}
        """
        
        # Execute the query with parameter binding for the vector
        print("Executing vector search via N1QL query...")
        result = cluster.query(
            vector_query,
            query_context=f'default:`{CB_BUCKET}`.`{CB_SCOPE}`',
            parameters={'query_vector': query_embedding}
        )
        
        # Process results
        scored_results = []
        for row in result:
            # Calculate similarity score (1 - distance)
            # Assuming distance is normalized between 0-1
            distance = row.get('distance_score', 0)
            similarity = 1 - distance
            
            result_item = {
                "hotel_name": row.get("hotel_name", "Unknown Hotel"),
                "review_content": row.get("review_content", "No content available"),
                "review_author": row.get("review_author", "Anonymous"),
                "review_date": row.get("review_date", "Unknown date"),
                "similarity_score": f"{similarity:.2f}",
                "ratings": row.get("review_ratings", {})
            }
            scored_results.append(result_item)
        
        print(f"Found {len(scored_results)} relevant documents using N1QL query")
        return scored_results
    except Exception as e:
        print(f"N1QL fallback failed: {e}")
        traceback.print_exc()
        return []

def fallback_search(user_input, top_k=5):
    """
    Basic fallback search method that retrieves documents when vector search is unavailable.
    
    Args:
        user_input (str): User's query text
        top_k (int): Number of results to return
        
    Returns:
        list: List of search results (without similarity scores)
    """
    try:
        # Connect to Couchbase
        cluster = connect_to_capella()
        bucket = cluster.bucket(CB_BUCKET)
        scope = bucket.scope(CB_SCOPE)
        collection = scope.collection(CB_COLLECTION_TARGET)
        
        # Simple N1QL query to get some documents
        query = f"""
        SELECT META().id as doc_id
        FROM `{CB_BUCKET}`.`{CB_SCOPE}`.`{CB_COLLECTION_TARGET}`
        LIMIT {top_k}
        """
        result = cluster.query(query)
        
        # Get documents using KV operations
        scored_results = []
        for row in result:
            doc_id = row["doc_id"]
            try:
                # Get the document with more detailed error handling
                get_result = collection.get(doc_id)
                
                # Handle different SDK versions - some use result.content, others use result.value
                doc = None
                if hasattr(get_result, 'content'):
                    doc = get_result.content
                elif hasattr(get_result, 'value'):
                    doc = get_result.value
                else:
                    print(f"Debug: GetResult attributes: {dir(get_result)}")
                    # Try to get the document content in any available way
                    for attr in dir(get_result):
                        if attr.startswith('_') or attr in ('id', 'cas', 'flags', 'expiry'):
                            continue
                        try:
                            val = getattr(get_result, attr)
                            if isinstance(val, dict) and not callable(val):
                                print(f"Using attribute {attr} as document content")
                                doc = val
                                break
                        except:
                            pass
                
                if doc is None:
                    print(f"Could not extract document content from GetResult for {doc_id}")
                    continue
                
                # Add to results with a placeholder similarity score
                result_item = {
                    "hotel_name": doc.get("hotel_name", "Unknown Hotel"),
                    "review_content": doc.get("review_content", "No content available"),
                    "review_author": doc.get("review_author", "Anonymous"),
                    "review_date": doc.get("review_date", "Unknown date"),
                    "similarity_score": "N/A (fallback)",
                    "ratings": doc.get("review_ratings", {})
                }
                scored_results.append(result_item)
            except Exception as e:
                print(f"Error retrieving document {doc_id}: {e}")
                traceback.print_exc()
                continue
        
        return scored_results
    except Exception as e:
        print(f"Fallback search also failed: {e}")
        traceback.print_exc()
        return [{"error": f"Search failed: {str(e)}"}]

def perform_vector_search(user_input, top_k=5):
    """
    Performs vector search using Couchbase's native vector search capabilities.
    Includes fallback mechanisms for different SDK versions and environments.
    
    Args:
        user_input (str): User's query text
        top_k (int): Number of top results to return
        
    Returns:
        list: List of search results with similarity scores
    """
    try:
        # Connect to Couchbase
        cluster = connect_to_capella()
        if cluster is None:
            print("Error: Failed to connect to Couchbase")
            return fallback_search(user_input, top_k)
            
        # Check if index exists
        if not check_vector_search_index(cluster):
            print("Warning: Vector search index not found, falling back to basic search")
            return fallback_search(user_input, top_k)
            
        bucket = cluster.bucket(CB_BUCKET)
        scope = bucket.scope(CB_SCOPE)
        
        # Generate embedding for the user input
        query_embedding = model.encode(user_input).tolist()
        
        print("Executing vector search using Search API...")
        
        # Debug the search capabilities
        print("Available search module attributes:", dir(search))
        
        try:
            # First attempt with the approach from the example
            # Create a search request with vector search component
            search_req = search.SearchRequest.create(search.MatchNoneQuery()).with_vector_search(
                VectorSearch.from_vector_query(VectorQuery('embedding', query_embedding, num_candidates=100))
            )
            
            # Execute the search
            result = scope.search(
                VECTOR_INDEX_NAME, 
                search_req, 
                SearchOptions(
                    limit=top_k,
                    fields=["hotel_name", "review_content", "review_author", "review_date", "review_ratings"]
                )
            )
        except AttributeError as ae:
            print(f"Search API method not found: {ae}")
            print("Trying alternative search approach...")
            
            # Alternative approach for older SDKs
            try:
                # Try direct vector search if available
                if hasattr(cluster, 'search_query'):
                    vector_query = search.VectorQuery('embedding', query_embedding)
                    result = cluster.search(VECTOR_INDEX_NAME, vector_query, 
                              SearchOptions(limit=top_k, fields=["hotel_name", "review_content", "review_author", "review_date", "review_ratings"]))
                else:
                    # Fall back to N1QL with vector functions
                    print("Search API not compatible, falling back to N1QL query")
                    return fallback_to_n1ql(cluster, query_embedding, top_k)
            except Exception as e2:
                print(f"Alternative search approach failed: {e2}")
                return fallback_search(user_input, top_k)
        
        # Process the results
        scored_results = []
        try:
            # Debug information
            print(f"Result type: {type(result)}")
            print(f"Result attributes: {dir(result)}")
            
            # Check if rows() method exists and is callable
            if hasattr(result, 'rows') and callable(result.rows):
                rows = result.rows()
                print(f"Number of rows: {len(list(rows)) if rows else 0}")
                
                # Reset rows iterator (since we consumed it above)
                rows = result.rows()
                
                for row in rows:
                    if row is None:
                        print("Warning: row is None, skipping")
                        continue
                        
                    print(f"Row type: {type(row)}")
                    print(f"Row attributes: {dir(row)}")
                    
                    # Check if fields() method exists and is callable
                    if hasattr(row, 'fields') and callable(row.fields):
                        fields = row.fields()
                    else:
                        print("Warning: row.fields() is not callable, trying alternative approaches")
                        # Try alternative ways to get fields
                        if hasattr(row, '_fields') and isinstance(row._fields, dict):
                            fields = row._fields
                        elif hasattr(row, 'value') and isinstance(row.value, dict):
                            fields = row.value
                        elif hasattr(row, 'data') and isinstance(row.data, dict):
                            fields = row.data
                        else:
                            print("Cannot extract fields from row, skipping")
                            continue
                    
                    # Calculate similarity score
                    if hasattr(row, 'score') and callable(row.score):
                        similarity = 1 - row.score()
                    elif hasattr(row, '_score'):
                        similarity = 1 - row._score
                    else:
                        similarity = 0
                        print("Warning: could not get score from row")
                    
                    result_item = {
                        "hotel_name": fields.get("hotel_name", "Unknown Hotel"),
                        "review_content": fields.get("review_content", "No content available"),
                        "review_author": fields.get("review_author", "Anonymous"),
                        "review_date": fields.get("review_date", "Unknown date"),
                        "similarity_score": f"{similarity:.2f}",
                        "ratings": fields.get("review_ratings", {})
                    }
                    scored_results.append(result_item)
            else:
                print("Warning: result.rows() is not callable, trying alternative approaches")
                # Try to extract results directly from the result object
                if hasattr(result, 'hits') and isinstance(result.hits, list):
                    for hit in result.hits:
                        fields = hit.get('fields', {})
                        similarity = 1 - hit.get('score', 0)
                        
                        result_item = {
                            "hotel_name": fields.get("hotel_name", "Unknown Hotel"),
                            "review_content": fields.get("review_content", "No content available"),
                            "review_author": fields.get("review_author", "Anonymous"),
                            "review_date": fields.get("review_date", "Unknown date"),
                            "similarity_score": f"{similarity:.2f}",
                            "ratings": fields.get("review_ratings", {})
                        }
                        scored_results.append(result_item)
                else:
                    print("Could not extract results from search response")
                    raise ValueError("No compatible methods found to extract search results")
                    
        except Exception as e:
            print(f"Error processing search results: {e}")
            traceback.print_exc()
            
        print(f"Found {len(scored_results)} relevant documents")
        return scored_results
    
    except Exception as e:
        print(f"Error performing vector search: {e}")
        traceback.print_exc()
        
        # Fallback to a basic KV operation approach if vector search fails
        print("Attempting fallback approach with basic document retrieval...")
        return fallback_search(user_input, top_k)

def display_results(results):
    """
    Formats and displays search results to the user.
    
    Args:
        results (list): List of search result items
    """
    if not results:
        print("No relevant reviews found.")
        return
    
    if "error" in results[0]:
        print(f"Error: {results[0]['error']}")
        return
    
    print("\n" + "="*80)
    print(f"Found {len(results)} relevant reviews:\n")
    
    for i, result in enumerate(results, 1):
        print(f"Result {i} (Similarity: {result['similarity_score']})")
        print(f"Hotel: {result['hotel_name']}")
        print(f"Review: {result['review_content']}")
        print(f"Author: {result['review_author']} - Date: {result['review_date']}")
        
        # Add ratings if available
        if result['ratings']:
            print("Ratings:")
            for category, rating in result['ratings'].items():
                print(f"- {category}: {rating}")
        
        print("-"*80)

def main():
    """
    Main function to run the CLI chatbot.
    Handles user input, vector search, and result display.
    """
    try:
        # Print SDK version for debugging
        import couchbase
        print(f"Couchbase Python SDK Version: {couchbase.__version__}")
        
        # Test connection first
        print("Testing connection to Couchbase...")
        cluster = connect_to_capella()
        if cluster is None:
            print("Error: Failed to connect to Couchbase. cluster object is None.")
            return
            
        print("Connection test successful!")
        print("\nWelcome to the Hotel Review Chatbot!")
        print("Ask questions about hotel experiences, and I'll find the most relevant reviews!")
        print("Type 'exit' or 'quit' to end the session.\n")
        
        while True:
            # Get user input
            user_input = input("\nYour question: ")
            
            # Check if user wants to exit
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Thank you for using the Hotel Review Chatbot. Goodbye!")
                break
            
            if not user_input.strip():
                print("Please enter a question or topic about hotel experiences.")
                continue
            
            # Perform vector search
            print("Searching for relevant reviews...")
            search_results = perform_vector_search(user_input)
            
            # Display results
            display_results(search_results)
            
    except KeyboardInterrupt:
        print("\nSession terminated by user. Goodbye!")
    except Exception as e:
        print(f"\nAn error occurred: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()
