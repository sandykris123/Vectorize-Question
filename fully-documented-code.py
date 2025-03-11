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
from datetime import timedelta

# Print SDK version
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
# Vector search index name - just use the base name without bucket/scope prefix
VECTOR_INDEX_NAME = "rv_idx"  # Changed from "travel-sample.inventory.rv_idx"

# Path to the Capella certificate file
CERT_PATH = "/Users/sandhya.krishnamurthy/Downloads/AIchatbot/AIDEMOCLUSTER-root-certificate.pem"

# Check if certificate exists
if not os.path.exists(CERT_PATH):
    print(f"Error: Capella certificate file not found at {CERT_PATH}")
    print("Download your certificate from Capella dashboard and update the CERT_PATH")
    sys.exit(1)

# Function to connect to Couchbase Capella
def connect_to_capella():
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
        return cluster
    except Exception as e:
        print(f"Connection error: {e}")
        print("\nTroubleshooting steps:")
        print("1. Verify your Capella username and password are correct")
        print("2. Check that your Capella endpoint URL is correct")
        print("3. Ensure your certificate file is valid and in the correct location")
        print("4. Check that your IP address is allowed in Capella's allowed IP list")
        sys.exit(1)

# Function to display available search indexes (informational only)
def list_search_indexes(cluster):
    try:
        # Make sure cluster is not None
        if cluster is None:
            print("Error: cluster object is None")
            return
            
        try:
            # Try to get indexes using the Search API if available
            mgr = cluster.search_indexes()
            indexes = mgr.get_all_indexes()
            
            print("\nAvailable search indexes:")
            for idx in indexes:
                print(f"  - {idx.name} (Bucket: {idx.bucket_name}, Scope: {idx.scope_name}, Collection: {idx.collection_name})")
                
            print(f"\nWe will use the index name '{VECTOR_INDEX_NAME}' for searches")
            print(f"Make sure this index exists in bucket '{CB_BUCKET}', scope '{CB_SCOPE}'\n")
            
        except Exception as se:
            print(f"Cannot list search indexes: {se}")
            
    except Exception as e:
        print(f"Error listing search indexes: {e}")
        import traceback
        traceback.print_exc()

# Function to perform vector search
def perform_vector_search(user_input, top_k=5):
    try:
        # Connect to Couchbase
        cluster = connect_to_capella()
        if cluster is None:
            print("Error: Failed to connect to Couchbase")
            return []
            
        bucket = cluster.bucket(CB_BUCKET)
        scope = bucket.scope(CB_SCOPE)
        collection = scope.collection(CB_COLLECTION_TARGET)
        
        # Generate embedding for the user input
        query_embedding = model.encode(user_input).tolist()
        
        print("Attempting vector search using Search API...")
        
        try:
            # Create a search request with vector search component
            search_req = search.SearchRequest.create(search.MatchNoneQuery()).with_vector_search(
                VectorSearch.from_vector_query(VectorQuery('embedding', query_embedding, num_candidates=100))
            )
            
            # Execute the search directly on the scope
            result = scope.search(
                VECTOR_INDEX_NAME,  # Use just the index name without bucket.scope prefix
                search_req,
                SearchOptions(
                    limit=top_k,
                    fields=["hotel_name", "review_content", "review_author", "review_date", "review_ratings"]
                )
            )
        except Exception as e:
            print(f"Search API error with SearchRequest: {e}")
            print("Trying alternative direct vector search...")
            
            # Simplified alternative approach
            vector_query = search.VectorQuery('embedding', query_embedding)
            result = scope.search(
                VECTOR_INDEX_NAME,
                vector_query,
                SearchOptions(
                    limit=top_k,
                    fields=["hotel_name", "review_content", "review_author", "review_date", "review_ratings"]
                )
            )
        
        # Process the results
        scored_results = []
        
        # Print result info for debugging
        print(f"Result type: {type(result)}")
        if hasattr(result, '__dict__'):
            print(f"Result __dict__: {result.__dict__}")
        
        # First try to use direct hits if available
        if hasattr(result, 'hits') and isinstance(result.hits, list):
            print(f"Found {len(result.hits)} hits directly in result.hits")
            
            for hit in result.hits:
                if isinstance(hit, dict) and 'fields' in hit:
                    fields = hit['fields']
                    score = hit.get('score', 0)
                    
                    result_item = {
                        "hotel_name": fields.get("hotel_name", "Unknown Hotel"),
                        "review_content": fields.get("review_content", "No content available"),
                        "review_author": fields.get("review_author", "Anonymous"),
                        "review_date": fields.get("review_date", "Unknown date"),
                        "similarity_score": f"{1-score:.2f}",
                        "ratings": fields.get("review_ratings", {})
                    }
                    scored_results.append(result_item)
            
            if scored_results:
                print(f"Successfully extracted {len(scored_results)} results from hits")
                return scored_results
        
        # If no hits, use the regular rows method but fetch documents with KV
        try:
            # Get rows from the result
            rows = list(result.rows())
            print(f"Successfully collected {len(rows)} rows")
            
            # Process each row by fetching the document
            for row in rows:
                print(f"Processing row ID: {row.id}")
                
                # Get the document ID from the row
                doc_id = row.id
                
                # Fetch the actual document using the ID
                try:
                    # Get document from collection
                    doc_result = collection.get(doc_id)
                    doc_content = doc_result.content_as[dict]
                    
                    # Create result item from the document content
                    result_item = {
                        "hotel_name": doc_content.get("hotel_name", "Unknown Hotel"),
                        "review_content": doc_content.get("review_content", "No content available"),
                        "review_author": doc_content.get("review_author", "Anonymous"),
                        "review_date": doc_content.get("review_date", "Unknown date"),
                        "similarity_score": f"{1-row.score:.2f}",
                        "ratings": doc_content.get("review_ratings", {})
                    }
                    scored_results.append(result_item)
                    print(f"Successfully processed document: {doc_id}")
                    
                except Exception as doc_ex:
                    print(f"Error fetching document {doc_id}: {doc_ex}")
                    print("Trying an alternative approach...")
                    
                    # If we can't get the document directly, try a N1QL query as fallback
                    try:
                        query = f'SELECT hotel_name, review_content, review_author, review_date, review_ratings FROM `{CB_BUCKET}`.`{CB_SCOPE}`.`{CB_COLLECTION_TARGET}` WHERE META().id = "{doc_id}"'
                        query_result = cluster.query(query)
                        
                        # Check if we got results
                        rows_list = list(query_result)
                        if rows_list:
                            doc_content = rows_list[0]
                            
                            result_item = {
                                "hotel_name": doc_content.get("hotel_name", "Unknown Hotel"),
                                "review_content": doc_content.get("review_content", "No content available"),
                                "review_author": doc_content.get("review_author", "Anonymous"),
                                "review_date": doc_content.get("review_date", "Unknown date"),
                                "similarity_score": f"{1-row.score:.2f}",
                                "ratings": doc_content.get("review_ratings", {})
                            }
                            scored_results.append(result_item)
                            print(f"Successfully processed document using N1QL: {doc_id}")
                    except Exception as query_ex:
                        print(f"Error fetching document with N1QL: {query_ex}")
        
        except Exception as e:
            print(f"Error processing search results: {e}")
            import traceback
            traceback.print_exc()
        
        # Return the results
        print(f"Returning {len(scored_results)} results")
        return scored_results
    
    except CouchbaseException as ex:
        print(f"Error performing vector search: {ex}")
        import traceback
        traceback.print_exc()
        return []

# Function to display search results
def display_results(results):
    if not results:
        print("No relevant reviews found.")
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

# Main function to run the CLI chatbot
def main():
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
        
        # Display available search indexes
        list_search_indexes(cluster)
        
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
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
