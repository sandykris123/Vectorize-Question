# Couchbase Vector Search Chatbot

This repository contains a Python application that demonstrates how to use Couchbase's vector search capabilities to build a simple hotel review chatbot. The chatbot uses semantic search to find hotel reviews that are relevant to user queries.

## Features

- Semantic similarity search using embeddings
- Utilizes Couchbase's native vector search capabilities 
- Multiple fallback mechanisms for different Couchbase SDK versions
- Support for both Search API and N1QL with vector functions
- Interactive CLI interface for querying hotel reviews

## Prerequisites

- Python 3.8+
- Couchbase Server 7.1+ (with vector search capabilities)
- A Couchbase Capella account or a self-managed Couchbase cluster

## Dependencies

```
sentence-transformers>=2.2.0
couchbase>=4.0.0
```

## Installation

1. Clone this repository:
```bash
git clone https://github.com/yourusername/couchbase-vector-search-chatbot.git
cd couchbase-vector-search-chatbot
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install the required packages:
```bash
pip install -r requirements.txt
```

## Configuration

Before running the application, you need to update the connection details and paths in the script:

```python
# Couchbase Capella connection parameters
CB_USERNAME = "Administrator"  # Change this
CB_PASSWORD = "Password1!"     # Change this
CB_HOSTNAME = "cb.0pjzyc2efdadlu6.cloud.couchbase.com"  # Change this
CB_BUCKET = "travel-sample"
CB_SCOPE = "inventory"
CB_COLLECTION_TARGET = "reviewvector"
# Vector search index name
VECTOR_INDEX_NAME = "review_vector_idx"

# Path to the Capella certificate file (if using Capella)
CERT_PATH = "/path/to/certificate.pem"  # Change this
```

## Setting up Vector Search

### 1. Prepare your data

Before using this application, you need to have documents with vector embeddings in your Couchbase database. Each document should have:

- A text field (e.g., `review_content`)
- An embedding field (named `embedding`) containing the vector representation of the text

### 2. Create a Vector Search Index

You can create a vector search index through the Couchbase Web Console:

1. Go to Search → Add Index
2. Name the index `review_vector_idx` (or change the `VECTOR_INDEX_NAME` in the script)
3. Select your bucket, scope, and collection
4. Add a vector mapping for the `embedding` field with 384 dimensions (for all-MiniLM-L6-v2 model)
5. Save and build the index

## Usage

Run the application:

```bash
python hotel_review_chatbot.py
```

The application will:
1. Connect to your Couchbase cluster
2. Check for the existence of the vector search index
3. Start an interactive CLI session
4. Convert user queries to embeddings
5. Search for relevant hotel reviews using vector search
6. Display the results

Example interaction:
```
Your question: Where can I find a hotel with a nice pool?

Found 5 relevant reviews:

Result 1 (Similarity: 0.89)
Hotel: Oceanview Resort
Review: The infinity pool was amazing, with a beautiful view of the ocean. Perfect for relaxing after a day of sightseeing.
Author: JohnT - Date: 2023-04-15
```

## How It Works

1. **Text Encoding**: User queries are encoded into vector embeddings using the SentenceTransformer model.
2. **Vector Search**: The application searches for similar reviews using:
   - Native Search API with vector search (primary method)
   - N1QL with VECTOR_DISTANCE function (fallback method)
3. **Result Processing**: The application processes the search results and displays them to the user.

## Code Structure

- `connect_to_capella()`: Establishes connection to Couchbase
- `check_vector_search_index()`: Checks for and validates the vector search index
- `perform_vector_search()`: Primary function that performs vector search
- `fallback_to_n1ql()`: Fallback method using N1QL queries
- `fallback_search()`: Basic document retrieval if vector search is unavailable
- `display_results()`: Formats and displays search results
- `main()`: Main program loop and user interaction

## Troubleshooting

- If you see `QueryIndexNotFoundException`, you need to create the search index
- If you encounter SDK compatibility issues, the application will fall back to alternative methods
- Check the debug output for detailed information about errors

## Extending the Application

You can extend this application by:
- Adding more sophisticated result ranking
- Implementing a web interface
- Adding support for more data types
- Implementing question-answering capabilities
- Adding a feedback mechanism to improve search results

## License

[MIT License](LICENSE)
