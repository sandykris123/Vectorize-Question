# Import required libraries
from sentence_transformers import SentenceTransformer
from couchbase.auth import PasswordAuthenticator
from couchbase.cluster import Cluster
from couchbase.options import ClusterOptions, ClusterTimeoutOptions
import json
import uuid
import os
import sys

# Load the sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Couchbase Capella connection parameters
# Update these with your actual Capella connection details
CB_USERNAME = "Administrator"  # Your Capella username
CB_PASSWORD = "Password1!"  # Your Capella password
CB_HOSTNAME = "cb.0pjzyc2efdadlu6.cloud.couchbase.com"  # Your Capella endpoint
CB_BUCKET = "travel-sample"
CB_SCOPE = "inventory"
CB_COLLECTION_SOURCE = "hotel"
CB_COLLECTION_TARGET = "reviewvector"

# Path to the Capella certificate file
# Download this from your Capella dashboard
CERT_PATH = "/Users/sandhya.krishnamurthy/Downloads/AIchatbot/AIDEMOCLUSTER-root-certificate.pem"


# Check if certificate exists
if not os.path.exists(CERT_PATH):
    print(f"Error: Capella certificate file not found at {CERT_PATH}")
    print("Download your certificate from Capella dashboard and save it as 'capella.pem'")
    sys.exit(1)

# Connect to Couchbase Capella cluster
print(f"Connecting to Couchbase Capella at {CB_HOSTNAME}...")
try:
    # For Capella, we must use secure connections
    connection_string = f"couchbases://{CB_HOSTNAME}"
    
    # Set up authenticator with your Capella credentials
    auth = PasswordAuthenticator(CB_USERNAME, CB_PASSWORD)
    
    # Configure timeout options using timedelta (which is what Couchbase expects)
    from datetime import timedelta
    timeout_opts = ClusterTimeoutOptions(
        kv_timeout=timedelta(seconds=30),
        query_timeout=timedelta(seconds=75)
    )
    
    # Create cluster options with certificate path
    options = ClusterOptions(authenticator=auth, timeout_options=timeout_opts)
    
    # Set certificate path for TLS/SSL connections
    options.ssl_cert = CERT_PATH
    
    # Connect to the cluster
    cluster = Cluster(connection_string, options)
    
    # Test connection
    print("Testing connection...")
    cluster.ping()
    print("Successfully connected to Couchbase Capella")
except Exception as e:
    print(f"Connection error: {e}")
    print("\nTroubleshooting steps:")
    print("1. Verify your Capella username and password are correct")
    print("2. Check that your Capella endpoint URL is correct")
    print("3. Ensure your certificate file (capella.pem) is valid and in the correct location")
    print("4. Check that your IP address is allowed in Capella's allowed IP list")
    print("5. Verify the travel-sample bucket is installed in your Capella cluster")
    sys.exit(1)

# Open the bucket, scope, and collections
try:
    bucket = cluster.bucket(CB_BUCKET)
    scope = bucket.scope(CB_SCOPE)
    source_collection = scope.collection(CB_COLLECTION_SOURCE)
    
    # Check if target collection exists
    try:
        target_collection = scope.collection(CB_COLLECTION_TARGET)
        print(f"Collection '{CB_COLLECTION_TARGET}' exists")
    except Exception:
        print(f"Warning: Collection '{CB_COLLECTION_TARGET}' not found.")
        print("Please create it in the Capella UI before proceeding.")
        sys.exit(1)
except Exception as e:
    print(f"Error accessing collections: {e}")
    sys.exit(1)

# Define N1QL query to get all hotel documents
query = f"""
    SELECT META().id as doc_id, h.* 
    FROM `{CB_BUCKET}`.`{CB_SCOPE}`.`{CB_COLLECTION_SOURCE}` h
"""

# Function to extract reviews from a hotel document
def extract_reviews(hotel_doc):
    reviews = []
    if 'reviews' in hotel_doc and isinstance(hotel_doc['reviews'], list):
        for review in hotel_doc['reviews']:
            if 'content' in review:
                reviews.append({
                    'hotel_id': hotel_doc.get('doc_id'),
                    'hotel_name': hotel_doc.get('name', 'Unknown Hotel'),
                    'review_author': review.get('author', 'Anonymous'),
                    'review_date': review.get('date', ''),
                    'review_content': review['content'],
                    'review_ratings': review.get('ratings', {})
                })
    return reviews

# Execute the query
print("Retrieving hotel documents...")
try:
    result = cluster.query(query)
except Exception as e:
    print(f"Query error: {e}")
    sys.exit(1)

# Process each hotel document
processed_count = 0
review_count = 0

for hotel in result:
    # Extract hotel document
    hotel_doc = hotel

    # Extract reviews from the hotel document
    reviews = extract_reviews(hotel_doc)
    
    # Process each review
    for review in reviews:
        try:
            # Generate embedding for the review content
            review_text = review['review_content']
            embedding = model.encode(review_text).tolist()
            
            # Create document to store in the target collection
            vector_doc = {
                'hotel_id': review['hotel_id'],
                'hotel_name': review['hotel_name'],
                'review_author': review['review_author'],
                'review_date': review['review_date'],
                'review_content': review_text,
                'review_ratings': review['review_ratings'],
                'embedding': embedding
            }
            
            # Generate a unique ID for the review vector document
            doc_id = f"review_vector_{str(uuid.uuid4())}"
            
            # Insert the document into the target collection
            target_collection.upsert(doc_id, vector_doc)
            review_count += 1
        except Exception as e:
            print(f"Error processing review: {e}")
            continue
    
    processed_count += 1
    if processed_count % 10 == 0:
        print(f"Processed {processed_count} hotels, {review_count} reviews")

print(f"Finished processing {processed_count} hotels and {review_count} reviews")
print("All review vectors have been stored in the reviewvector collection")
