# GitHub Star Crawler

This project implements a GitHub crawler to obtain star counts for repositories using the GitHub GraphQL API and stores the data in a PostgreSQL database. It also includes a GitHub Actions pipeline for continuous crawling and data management.

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Setup and Local Run](#setup-and-local-run)
  - [Prerequisites](#prerequisites)
  - [Environment Variables](#environment-variables)
  - [Database Setup](#database-setup)
  - [Running the Crawler](#running-the-crawler)
- [GitHub Actions Pipeline](#github-actions-pipeline)
- [Scaling to 500 Million Repositories](#scaling-to-500-million-repositories)
- [Schema Evolution for More Metadata](#schema-evolution-for-more-metadata)

## Features

-   Crawls GitHub repositories via GraphQL API.
-   Collects repository ID, owner, name, URL, and star count.
-   Respects GitHub API rate limits with retry mechanisms.
-   Stores data in a PostgreSQL database with an efficient UPSERT strategy.
-   Includes a GitHub Actions workflow for automated setup, crawling, and database dumping.
-   Designed with clean architecture principles: separation of concerns, immutability (where applicable), and anti-corruption layer (API interaction isolated).

## Project Structure

```
github_crawler/
├── .github/
│   └── workflows/
│       └── main.yml        # GitHub Actions workflow
├── src/
│   ├── crawler.py          # Core logic for crawling GitHub API and saving to DB
│   └── setup_db.py         # Script to set up PostgreSQL database schema
├── .env.example            # Example file for environment variables
├── requirements.txt        # Python dependencies
└── README.md               # Project documentation
```

## Setup and Local Run

### Prerequisites

-   Python 3.9+
-   Docker (for running PostgreSQL locally)
-   `pip` for Python package management

### Environment Variables

Create a `.env` file in the `github_crawler/` directory based on `.env.example`:

```
GITHUB_TOKEN=YOUR_GITHUB_PERSONAL_ACCESS_TOKEN
DB_HOST=localhost
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=postgres
DB_PORT=5432
```

-   **`GITHUB_TOKEN`**: A GitHub Personal Access Token with `public_repo` scope. You can generate one from your [GitHub Developer Settings](https://github.com/settings/tokens).
-   **`DB_HOST`**, **`DB_NAME`**, **`DB_USER`**, **`DB_PASSWORD`**, **`DB_PORT`**: PostgreSQL connection details.

### Database Setup

1.  **Start a PostgreSQL Container:**
    ```bash
    docker run --name some-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 -d postgres:13
    ```
    (Adjust `POSTGRES_PASSWORD` if you're using a different one in your `.env`)

2.  **Install Python Dependencies:**
    ```bash
    pip install -r github_crawler/requirements.txt
    ```

3.  **Create Database Schema:**
    ```bash
    python github_crawler/src/setup_db.py
    ```

### Running the Crawler

After setting up the database and environment variables, you can run the crawler locally:

```bash
python github_crawler/src/crawler.py
```
The crawler will fetch repositories and store them in your local PostgreSQL database.

## GitHub Actions Pipeline

The `.github/workflows/main.yml` defines the CI/CD pipeline for this project.

1.  **`on: [push, workflow_dispatch]`**: The workflow runs on every push to the `main` branch and can also be triggered manually.
2.  **`services: postgres`**: A PostgreSQL 13 service container is spun up for the job, accessible at `localhost:5432` from within the job.
3.  **`Setup Python` & `Install dependencies`**: Sets up Python 3.9 and installs dependencies from `requirements.txt`.
4.  **`Setup PostgreSQL Schema`**: Executes `github_crawler/src/setup_db.py` to create the `repositories` table and necessary triggers/indexes in the service container's database.
5.  **`Crawl GitHub Stars`**: Executes `github_crawler/src/crawler.py`. It uses `secrets.GITHUB_TOKEN` (the default token provided by GitHub Actions) for API authentication.
6.  **`Dump Database Content`**: Uses `pg_dump` to create a SQL dump of the `repositories` table.
7.  **`Upload Database Dump as Artifact`**: The SQL dump is uploaded as a workflow artifact, allowing you to download the crawled data after each successful run.

The pipeline ensures that the default `GITHUB_TOKEN` is used and does not require elevated permissions, fulfilling the assignment requirements.

## Scaling to 500 Million Repositories

Scaling this crawler to handle 500 million repositories requires a fundamental shift from a single-node setup to a distributed, fault-tolerant architecture. Key considerations include:

1.  **Distributed Processing:**
    *   Break down the crawling task into smaller, manageable units processed by a **fleet of workers**.
    *   Use a **message queue** to distribute tasks reliably and handle communication between workers.
    *   Implement **idempotency** to ensure tasks can be retried without side effects.

2.  **API Strategy & Rate Limits:**
    *   Leverage **GitHub App Installation Tokens** for significantly higher rate limits than personal access tokens.
    *   Optimize **GraphQL queries** to fetch only essential data, reducing API cost and payload size.
    *   Implement a **centralized rate limiting service** to coordinate API calls across all distributed workers effectively.

3.  **Database Scalability:**
    *   Transition from a single PostgreSQL instance to a **sharded or partitioned database** solution to distribute data load.
    *   Utilize **managed database services** (e.g., AWS RDS) for simplified operations and inherent scaling capabilities.
    *   Consider a **data lake or data warehouse** for long-term storage and complex analytics, separating it from the operational database.

4.  **Operational Excellence:**
    *   Implement **distributed tracing** to monitor request flows across multiple services.
    *   Set up **comprehensive logging and alerting** for proactive identification of issues like rate limit exhaustion or crawl failures.

## Schema Evolution for More Metadata

When expanding to collect more detailed metadata (e.g., issues, pull requests, comments, commits, CI checks), the current schema's flexible design and efficient update strategy would be extended through:

1.  **Normalization:** Create dedicated tables for each new entity type (e.g., `pull_requests`, `issues`, `comments`, `commits`, `ci_checks`).
2.  **Relationships:** Establish explicit **foreign key relationships** between these new tables and the existing `repositories` table, and among themselves.
3.  **Efficient Updates (UPSERT):** Continue to use **UPSERT (ON CONFLICT DO UPDATE)** for data ingestion. This ensures that new entities are inserted, and existing ones are updated only on their changing fields, minimizing database load.
4.  **Selective Fetching:** Implement logic to fetch only new or updated metadata since the last crawl, rather than re-fetching all historical data.

This approach ensures that the database remains efficient and scalable, handling the continuous ingestion of diverse and frequently changing GitHub metadata.