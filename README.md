# immich-smart-search

immich-smart-search is a companion service for [Immich](https://immich.app) that enables advanced natural language search queries. It parses free-form text—extracting date ranges, locations, boolean flags (archived, favorite, motion), and camera make/model—and then generates a URL that directs the user to Immich with those advanced search parameters embedded.

The service is implemented using FastAPI, spaCy (with the transformer-based English model), dateparser, and geonamescache. It also provides a simple HTML front-end so that users can test and use the search functionality.

## Features

- **Natural Language Parsing:** Extracts search parameters such as:
  - **Date Filters:** For creation/taken dates (e.g., "from Jan 2024 to July 2024")
  - **Location:** City, state, and country (using spaCy + geonamescache)
  - **Boolean Flags:** e.g., archived, favorite, motion
  - **Camera Make/Model:** Detects common keywords like "iPhone", "Pixel", "Galaxy", etc.
- **URL Generation:** Constructs a URL that embeds the structured search query as JSON in the query string, allowing redirection to Immich’s search page.
- **Simple Front-End:** A basic HTML search form for testing the functionality.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) and [Docker Compose](https://docs.docker.com/compose/install/)
- A running Immich server. Users may need to configure networking so that the smart search service can reach the Immich server (via IP or Docker service name).

## Environment Variables

Create a `.env` file in the root of this repository (next to the Dockerfile and docker-compose.yml) with entries such as:

```ini
# The host or Docker service name of your Immich server.
IMMICH_HOST=immich-server

# The port on which Immich is accessible (default: 2283).
IMMICH_PORT=2283
```

> **Note:** When using Docker Compose in a multi-container setup, setting `IMMICH_HOST` to the Immich service name (e.g., `immich-server`) allows Docker’s internal DNS to resolve it correctly.

## Installation & Setup

### Clone the Repository

```bash
git clone https://github.com/syntax922/immich-smart-search.git
cd immich-smart-search
```

### Update the `.env` File

Edit the `.env` file to set the correct `IMMICH_HOST` and `IMMICH_PORT` for your Immich deployment.

### Build and Deploy with Docker Compose

Use the provided `docker-compose.yaml` file to build and run the service:

```bash
docker-compose up --build -d
```

This command builds the image for immich-smart-search and starts the container, mapping the container’s port 80 to host port 8080 (or as configured).

## Usage

### Access the Front-End

Open your browser and navigate to [http://localhost:8080](http://localhost:8080). You should see a simple search form.

### Perform a Search

Enter a query (e.g., *Show me archived favorites in Seattle, WA from Jan 2024 to July 2024 taken with an iPhone 14*) and click **Search**. The service will:

1. Parse the query to extract structured search parameters.
2. Build a URL (using the values from your `.env` file) that embeds these parameters.
3. Present a clickable link or redirect you to Immich’s search page with the advanced query applied.

### API Endpoints

- **GET `/health`**: Returns a simple JSON health check:

  ```json
  {"status": "ok"}
  ```

- **POST `/parse`**: Accepts a JSON payload with a `"query"` key and returns a JSON object with the parsed search parameters and the generated URL payload.

- **GET `/searchRedirect?query=...`**: Reads the query parameter, constructs the Immich search URL, and redirects the browser.

## Docker Compose

Below is an example `docker-compose.yaml` that builds and runs the smart search service:

```yaml
version: "3.8"

services:
  immich-smart-search:
    build: .
    container_name: immich_smart_search
    ports:
      - "8080:80"
    env_file:
      - .env
    restart: always
```

## Customization

### Parsing Logic

The core logic in `app/main.py` uses spaCy, dateparser, and geonamescache to interpret natural language. Modify this logic to handle additional cases or refine parsing accuracy.

### Front-End

The HTML front-end is minimal. Enhance it to better fit your deployment or integrate additional UI features if needed.

## Troubleshooting

### Model Loading Errors

Ensure that `en_core_web_trf` is installed correctly. The Dockerfile installs dependencies based on `requirements.txt`. If you encounter issues, verify that the transformer model is downloaded and installed.

### Networking Issues

If the Immich server isn’t reachable, check that `IMMICH_HOST` and `IMMICH_PORT` are correctly set and that your Docker network allows communication between containers.

## Contributing

Contributions, issues, and feature requests are welcome! Please open an issue or submit a pull request on the [GitHub repository](https://github.com/syntax922/immich-smart-search).

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
