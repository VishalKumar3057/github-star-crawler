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

Collecting data for 500 million repositories instead of 100,000 would require significant architectural changes and a distributed approach.

1.  **Distributed Crawling Architecture:**
    *   **Worker Pool:** Instead of a single crawler, a fleet of distributed workers (e.g., using Kubernetes, AWS Fargate, or similar container orchestration) would be needed. Each worker would process a subset of the crawling task.
    *   **Message Queue:** A robust message queue (e.g., Apache Kafka, AWS SQS) would be essential for distributing crawling tasks (e.g., specific GraphQL queries, cursor values) to workers and handling failures.
    *   **Centralized Rate Limiter:** With many workers, simply checking `X-RateLimit-Remaining` per worker is insufficient. A centralized, shared rate limiting service (e.g., using Redis) would be crucial to ensure the *aggregate* API calls respect GitHub's global rate limits for the entire system.
    *   **Idempotency:** Crawling tasks must be idempotent to handle retries and worker failures gracefully without duplicating data or causing inconsistencies.

2.  **Advanced API Strategy:**
    *   **GitHub App Installation Tokens:** Instead of a single Personal Access Token or `GITHUB_TOKEN`, using GitHub App installation tokens would provide significantly higher rate limits and better scalability for API access. Multiple installations could be used to further increase throughput.
    *   **GraphQL Query Optimization:** Even more aggressive optimization of GraphQL queries to fetch only absolutely necessary data. Potentially breaking down complex queries into simpler ones if it helps with rate limit cost.

3.  **Database Scaling:**
    *   **Horizontal Sharding/Partitioning:** A single PostgreSQL instance would become a bottleneck very quickly. The database would need to be sharded (partitioned) across multiple instances, perhaps based on a hash of the `repository_id` or `owner` name.
    *   **Managed Database Service:** Using a managed service like AWS RDS, Azure Database for PostgreSQL, or Google Cloud SQL would simplify operations, backups, and scaling capabilities.
    *   **Data Lake/Warehouse:** For analytical purposes, storing the raw crawled data in a data lake (e.g., S3, Google Cloud Storage) and then processing it into a data warehouse (e.g., Snowflake, Google BigQuery, AWS Redshift) would be more appropriate than solely relying on a transactional database for such vast amounts of data. This separates OLTP from OLAP concerns.

4.  **Error Handling and Monitoring:**
    *   **Distributed Tracing:** Tools like Jaeger or OpenTelemetry would be critical to trace requests across multiple services and identify bottlenecks or failures.
    *   **Comprehensive Logging & Alerting:** Centralized logging (e.g., ELK stack, Datadog) and proactive alerting on errors, rate limit exhaustion, or crawling stalls.

5.  **Data Quality and Consistency:**
    *   **Reconciliation Jobs:** Jobs to periodically reconcile data, identify missing repositories, or correct inconsistencies that might arise from distributed operations.
    *   **Versioning:** Consider data versioning if historical accuracy is paramount, allowing reconstruction of data at a specific point in time.

## Schema Evolution for More Metadata

The current schema is designed for flexibility and efficient updates. When extending to gather more metadata (issues, pull requests, commits, comments, reviews, CI checks), the key is **normalization** and leveraging the `id` field of each GitHub entity, along with `UPSERT` operations for efficient updates.

The core principle for efficient updates ("minimal rows affected") is to:
1.  **Create separate tables for each new entity type.**
2.  **Use foreign keys** to link these new entities back to the `repositories` table and to each other (e.g., comments link to issues/PRs).
3.  **Utilize `UPSERT` (ON CONFLICT DO UPDATE)** for data ingestion. When a new batch of data arrives, if an entity already exists (matched by its unique ID), only its changing fields (like `updated_at`, `status`, `body`, `comment_count`) are updated. New entities are inserted.
4.  **Selective Fetching/Crawling:** Instead of re-fetching all data, implement logic to only fetch new or updated metadata since the last crawl for a given repository/PR/issue.

Here's how the schema could evolve:

**1. `repositories` table (Current):**
```sql
CREATE TABLE repositories (
    id BIGINT PRIMARY KEY,
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    url VARCHAR(2048) NOT NULL,
    stars INT NOT NULL,
    crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**2. `pull_requests` table:**
-   Links to `repositories`.
-   `updated_at` trigger for efficient tracking of changes.
```sql
CREATE TABLE pull_requests (
    id BIGINT PRIMARY KEY,              -- GitHub's global PR ID
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    number INT NOT NULL,                -- PR number within the repository
    title TEXT NOT NULL,
    state VARCHAR(50) NOT NULL,         -- e.g., OPEN, CLOSED, MERGED
    author_login VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE,
    merged_at TIMESTAMP WITH TIME ZONE,
    comments_count INT DEFAULT 0,       -- Denormalized count for quick access
    commits_count INT DEFAULT 0,
    review_comments_count INT DEFAULT 0,
    -- Add more fields as needed (e.g., baseRefName, headRefName, additions, deletions)
    UNIQUE (repository_id, number)      -- Ensure unique PR per repo
);

-- Trigger to update 'updated_at' on changes
CREATE TRIGGER update_pull_requests_updated_at
BEFORE UPDATE ON pull_requests
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**3. `issues` table:**
-   Similar to `pull_requests`, but distinct.
```sql
CREATE TABLE issues (
    id BIGINT PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    number INT NOT NULL,
    title TEXT NOT NULL,
    state VARCHAR(50) NOT NULL,         -- e.g., OPEN, CLOSED
    author_login VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE,
    comments_count INT DEFAULT 0,
    -- Add more fields (e.g., labels, assignees)
    UNIQUE (repository_id, number)
);

CREATE TRIGGER update_issues_updated_at
BEFORE UPDATE ON issues
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**4. `comments` table (for both PRs and Issues):**
-   A flexible design using `polymorphic association` with `commentable_type` and `commentable_id`.
```sql
CREATE TABLE comments (
    id BIGINT PRIMARY KEY,
    author_login VARCHAR(255),
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    commentable_type VARCHAR(50) NOT NULL, -- 'pull_request' or 'issue'
    commentable_id BIGINT NOT NULL,        -- References pull_requests.id or issues.id
    -- Add foreign key constraints conditionally or handle in application logic
    -- e.g., CHECK ( (commentable_type = 'pull_request' AND commentable_id IN (SELECT id FROM pull_requests)) OR ... )
);

CREATE INDEX idx_comments_on_commentable ON comments (commentable_type, commentable_id);

CREATE TRIGGER update_comments_updated_at
BEFORE UPDATE ON comments
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```
*Note: Direct SQL foreign key constraints for polymorphic associations are complex. Often, this is managed at the application level.*

**5. `commits` table (within PRs):**
-   Links to `pull_requests`.
```sql
CREATE TABLE commits (
    id BIGINT PRIMARY KEY,              -- Commit SHA (can be VARCHAR) or GitHub's Commit ID
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    sha VARCHAR(40) UNIQUE NOT NULL,    -- Commit SHA
    author_login VARCHAR(255),
    message TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    -- Add more fields (e.g., parents, files changed, additions, deletions)
    UNIQUE (pull_request_id, sha)
);

-- No `updated_at` trigger typically needed for commits as they are immutable.
```

**6. `reviews` table (on PRs):**
```sql
CREATE TABLE reviews (
    id BIGINT PRIMARY KEY,
    pull_request_id BIGINT NOT NULL REFERENCES pull_requests(id) ON DELETE CASCADE,
    author_login VARCHAR(255),
    state VARCHAR(50) NOT NULL,         -- e.g., APPROVED, CHANGES_REQUESTED, COMMENTED
    submitted_at TIMESTAMP WITH TIME ZONE NOT NULL,
    body TEXT,
    -- Add more fields (e.g., commit_id if review is on a specific commit)
);

-- No `updated_at` trigger typically needed for reviews as they are submitted once.
```

**7. `ci_checks` table:**
```sql
CREATE TABLE ci_checks (
    id BIGINT PRIMARY KEY,
    repository_id BIGINT NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    pull_request_id BIGINT REFERENCES pull_requests(id) ON DELETE SET NULL, -- Optional link to PR
    name VARCHAR(255) NOT NULL,         -- e.g., 'build', 'test', 'lint'
    status VARCHAR(50) NOT NULL,        -- e.g., 'SUCCESS', 'FAILURE', 'PENDING'
    conclusion VARCHAR(50),             -- e.g., 'SUCCESS', 'FAILURE', 'NEUTRAL'
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    url VARCHAR(2048),
    -- Add more fields (e.g., head_sha)
    UNIQUE (repository_id, id) -- CI checks might have unique IDs per repo
);

CREATE TRIGGER update_ci_checks_updated_at
BEFORE UPDATE ON ci_checks
FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
```

**Efficient Updates with this Schema:**

For example, when crawling a PR for comments:
-   Fetch comments for a given `pull_request_id` that were created/updated since the last crawl.
-   For each fetched comment, perform an `UPSERT` into the `comments` table using its `id` as the conflict target. If the comment already exists, `updated_at` will be refreshed, and its `body` might be updated if GitHub allows comment edits. If it's new, it's inserted. This affects only the `comments` table.
-   The `pull_requests.comments_count` could be updated by a separate periodic job or a trigger, or updated in the crawler itself after processing all comments for a PR.

This normalized and UPSERT-driven approach ensures that each piece of metadata is stored in its appropriate table, and updates are performed with minimal row changes, leading to an efficient and scalable data model.
#   g i t h u b - s t a r - c r a w l e r  
 