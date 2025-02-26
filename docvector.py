
from sentence_transformers import SentenceTransformer
model = SentenceTransformer('all-MiniLM-L6-v2')  # Downloads once, then uses locally

# 3. Generate embeddings
sentences = ["hotels with excellent review"]
embeddings = model.encode(sentences)

print(f"Embedding shape: {embeddings.shape}")  # Should be (2, 384)
print(f"First embedding: {embeddings[0][:500]}...")  # Print first 5 values
