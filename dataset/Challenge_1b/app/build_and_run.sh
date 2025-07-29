#!/bin/bash

# Build the Docker image
echo "Building Docker image..."
docker build -t challenge1b-app .

# Run the container
echo "Running the container..."
docker run --rm \
  -v "$(pwd)/input:/app/input" \
  -v "$(pwd)/output:/app/output" \
  challenge1b-app

echo "Processing complete! Check the output directory for results." 