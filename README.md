# Challenge 1B - PDF Processing App

This Docker application processes PDF documents to extract and analyze sections and subsections based on a given persona and job-to-be-done.

## Prerequisites

- Docker installed on your system
- PDF files to process in the `input/` directory

## Quick Start

### Option 1: Using the build script
```bash
# Make the script executable
chmod +x build_and_run.sh

# Run the script
./build_and_run.sh
```

### Option 2: Manual Docker commands

1. **Build the Docker image:**
   ```bash
   docker build -t challenge1b-app .
   ```

2. **Run the container:**
   ```bash
   docker run --rm \
     -v "$(pwd)/input:/app/input" \
     -v "$(pwd)/output:/app/output" \
     challenge1b-app
   ```

## Input Requirements

Place your PDF files in the `input/` directory. The application expects:

- PDF files to process
- A `config.json` file with:
  - `persona`: Description of the target user
  - `job_to_be_done`: The specific task or goal

Example `config.json`:
```json
{
  "persona": "A travel enthusiast planning a trip to the South of France",
  "job_to_be_done": "Find relevant information about destinations, activities, and practical travel tips for a comprehensive South of France travel experience"
}
```

## Output

The processed results will be saved in the `output/` directory:

- `output.json`: Main output with extracted sections and subsection analysis
- Individual JSON files for each processed PDF (Round 1A format)

## Docker Image Features

- **Security**: Runs as non-root user
- **Optimization**: Multi-stage build with proper caching
- **Dependencies**: Includes all required Python packages and NLTK data
- **Error Handling**: Proper environment setup and error handling

## Troubleshooting

1. **Permission issues**: The container runs as a non-root user. Ensure input/output directories have proper permissions.

2. **Missing config.json**: Make sure `input/config.json` exists with the required fields.

3. **Memory issues**: The sentence transformer model requires significant memory. Ensure your Docker has adequate resources allocated.

## Development

To modify the application:

1. Edit the Python files in the app directory
2. Rebuild the Docker image: `docker build -t challenge1b-app .`
3. Run the container as described above 