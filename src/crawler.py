
import os
import time
import requests
import psycopg2
from dotenv import load_dotenv
from datetime import datetime, timezone # Added import for datetime and timezone

# Load environment variables from .env file
load_dotenv()

class GitHubCrawler:
    def __init__(self):
        self.github_token = os.getenv("GITHUB_TOKEN")
        if not self.github_token:
            raise ValueError("GITHUB_TOKEN environment variable not set.")

        self.db_host = os.getenv("DB_HOST", "localhost")
        self.db_name = os.getenv("DB_NAME", "postgres")
        self.db_user = os.getenv("DB_USER", "postgres")
        self.db_password = os.getenv("DB_PASSWORD", "postgres")
        self.db_port = os.getenv("DB_PORT", "5432")
        self.api_url = "https://api.github.com/graphql"
        self.headers = {
            "Authorization": f"Bearer {self.github_token}",
            "Content-Type": "application/json",
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.collected_repos_count = 0

    def _handle_rate_limit(self, headers_or_data):
        """Calculates wait time based on rate limit reset and sleeps."""
        reset_time = None
        if isinstance(headers_or_data, dict): # GraphQL rateLimit data
            reset_at_str = headers_or_data.get("resetAt")
            if reset_at_str:
                # GitHub returns ISO 8601 format, e.g., "2023-11-20T12:34:56Z"
                # Need to replace 'Z' with '+00:00' for fromisoformat to work with Python < 3.11 for UTC
                reset_time_dt = datetime.fromisoformat(reset_at_str.replace("Z", "+00:00"))
                reset_time = reset_time_dt.timestamp()
        else: # HTTP Headers
            reset_time = headers_or_data.get("X-RateLimit-Reset")
            if reset_time:
                reset_time = int(reset_time)

        if reset_time:
            now = time.time()
            wait_time = max(0, reset_time - now + 5) # Add a buffer of 5 seconds
            print(f"Rate limit will reset at {time.ctime(reset_time)}. Waiting for {int(wait_time)} seconds.")
            time.sleep(wait_time)
        else:
            print("Could not determine rate limit reset time. Waiting for 60 seconds as a precaution.")
            time.sleep(60)
        return True # Indicate that a wait occurred

    def _check_graphql_response_for_errors_and_ratelimit(self, data, response_headers):
        """
        Checks a parsed GraphQL response for errors or rate limit warnings.
        Returns True if a retry is needed due to rate limiting, False otherwise.
        """
        if "errors" in data:
            print(f"GraphQL errors: {data['errors']}")
            for error in data["errors"]:
                if "message" in error and "rate limit" in error["message"].lower():
                    print("GraphQL rate limit error encountered. Waiting for reset...")
                    return self._handle_rate_limit(response_headers) # Pass HTTP headers for reset time
            return False # Non-rate limit GraphQL error, no retry

        if "data" in data and "rateLimit" in data["data"]:
            rate_limit = data["data"]["rateLimit"]
            print(f"Rate Limit: Cost={rate_limit['cost']}, Remaining={rate_limit['remaining']}, Reset At={rate_limit['resetAt']}")
            # Proactive rate limit handling: wait if approaching limit
            if rate_limit["remaining"] < rate_limit["cost"] + 10: # Keep a buffer
                print("Approaching rate limit. Waiting for reset...")
                return self._handle_rate_limit(rate_limit) # Pass GraphQL data for reset time
        return False # No retry needed

    def _execute_query(self, query, variables=None):
        """Executes a GraphQL query with rate limit handling and retries."""
        retries = 0
        max_retries = 5 # Limit the number of retries for connection/timeout errors

        while retries < max_retries:
            try:
                response = self.session.post(self.api_url, json={"query": query, "variables": variables})
                response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
                data = response.json()

                if self._check_graphql_response_for_errors_and_ratelimit(data, response.headers):
                    # Rate limit handled, retry the request
                    retries = 0 # Reset retries after a successful wait
                    continue

                return data # Return data if no errors or rate limits requiring retry

            except requests.exceptions.HTTPError as e:
                print(f"HTTP error occurred: {e}. Status Code: {e.response.status_code}")
                if e.response.status_code == 401:
                    raise ValueError("Unauthorized: Check your GITHUB_TOKEN.")
                elif e.response.status_code == 403: # Forbidden, often due to rate limits
                    print("Forbidden. Possible rate limit. Waiting for reset...")
                    if self._handle_rate_limit(e.response.headers):
                        retries = 0 # Reset retries after a successful wait
                        continue # Retry after handling rate limit
                    else:
                        print("Failed to handle 403 (Forbidden) error. Aborting.")
                        raise # Re-raise if rate limit couldn't be handled
                else:
                    print(f"Unhandled HTTP error, retrying in 10 seconds (attempt {retries + 1}/{max_retries})...")
                    retries += 1
                    time.sleep(10)
                    continue # Retry for other HTTP errors

            except requests.exceptions.ConnectionError as e:
                print(f"Connection error occurred: {e}. Retrying in 10 seconds (attempt {retries + 1}/{max_retries})...")
                retries += 1
                time.sleep(10)
                continue
            except requests.exceptions.Timeout as e:
                print(f"Timeout error occurred: {e}. Retrying in 10 seconds (attempt {retries + 1}/{max_retries})...")
                retries += 1
                time.sleep(10)
                continue
            except Exception as e:
                print(f"An unexpected error occurred: {e}")
                raise

        print(f"Max retries ({max_retries}) reached. Aborting query.")
        return None # Return None if max retries exceeded

    def _get_db_connection(self):
        """Establishes a connection to the PostgreSQL database."""
        return psycopg2.connect(
            host=self.db_host,
            dbname=self.db_name,
            user=self.db_user,
            password=self.db_password,
            port=self.db_port
        )

    def _save_repositories(self, repositories):
        """Saves a list of repositories to the database using UPSERT."""
        conn = None
        try:
            conn = self._get_db_connection()
            cur = conn.cursor()
            for repo in repositories:
                repo_id = repo["id"]
                owner = repo["owner"]["login"]
                name = repo["name"]
                url = repo["url"]
                stars = repo["stargazerCount"]

                upsert_query = """
                    INSERT INTO repositories (id, owner, name, url, stars)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        owner = EXCLUDED.owner,
                        name = EXCLUDED.name,
                        url = EXCLUDED.url,
                        stars = EXCLUDED.stars,
                        updated_at = NOW();
                """
                cur.execute(upsert_query, (repo_id, owner, name, url, stars))
            conn.commit()
            cur.close()
            print(f"Saved {len(repositories)} repositories to the database.")
        except (Exception, psycopg2.DatabaseError) as error:
            print(f"Error saving repositories to DB: {error}")
            if conn:
                conn.rollback()
        finally:
            if conn:
                conn.close()

    def crawl_repositories(self, target_count=100000, batch_size=100):
        """Crawls GitHub for repositories and saves them to the database."""
        query = """
            query ($cursor: String) {
              rateLimit {
                cost
                remaining
                resetAt
              }
              search(query: "stars:>1", type: REPOSITORY, first: %s, after: $cursor) {
                pageInfo {
                  endCursor
                  hasNextPage
                }
                nodes {
                  ... on Repository {
                    id
                    name
                    url
                    stargazerCount
                    owner {
                      login
                    }
                  }
                }
              }
            }
        """ % batch_size

        next_cursor = None
        while self.collected_repos_count < target_count:
            print(f"Collected {self.collected_repos_count}/{target_count} repositories. Fetching next batch...")
            variables = {"cursor": next_cursor}
            result = self._execute_query(query, variables)

            if not result or "data" not in result or "search" not in result["data"]:
                print("Failed to fetch data or no more results.")
                break

            search_data = result["data"]["search"]
            repositories = search_data["nodes"]
            page_info = search_data["pageInfo"]

            if repositories:
                self._save_repositories(repositories)
                self.collected_repos_count += len(repositories)
            else:
                print("No repositories found in the current batch.")

            if not page_info["hasNextPage"] or self.collected_repos_count >= target_count:
                print("No more pages or target count reached.")
                break
            next_cursor = page_info["endCursor"]

        print(f"Finished crawling. Total repositories collected: {self.collected_repos_count}")

if __name__ == "__main__":
    try:
        crawler = GitHubCrawler()
        crawler.crawl_repositories()
    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e:
        print(f"An error occurred during crawling: {e}")

