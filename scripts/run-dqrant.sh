mkdir -p data/qdrant
docker run -d --name zcs-qdrant \
  -p 6333:6333 -p 6334:6334 \
  -v "$PWD/data/qdrant:/qdrant/storage" \
  qdrant/qdrant:latest