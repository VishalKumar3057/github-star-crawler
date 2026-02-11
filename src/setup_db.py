
import os
import psycopg2
from psycopg2 import sql

def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        dbname=os.getenv("DB_NAME", "postgres"),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        port=os.getenv("DB_PORT", "5432")
    )

def setup_database():
    """Sets up the database schema."""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()

        # Drop table and related objects if they exist to apply schema changes easily
        cur.execute("DROP TRIGGER IF EXISTS update_repositories_updated_at ON repositories;")
        cur.execute("DROP TABLE IF EXISTS repositories CASCADE;") # CASCADE drops dependent objects like indexes

        cur.execute("""
            CREATE TABLE repositories (
                id VARCHAR(255) PRIMARY KEY, -- Changed from BIGINT to VARCHAR to store GitHub's Base64 IDs
                owner VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                url VARCHAR(2048) NOT NULL,
                stars INT NOT NULL,
                crawled_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_repositories_owner_name ON repositories (owner, name);
        """)

        cur.execute("""
            CREATE OR REPLACE FUNCTION update_updated_at_column()
            RETURNS TRIGGER AS $$
            BEGIN
               NEW.updated_at = NOW(); 
               RETURN NEW;
            END;
            $$ language 'plpgsql';
        """)

        cur.execute("""
            CREATE TRIGGER update_repositories_updated_at
            BEFORE UPDATE ON repositories
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)

        conn.commit()
        cur.close()
        print("Database setup completed successfully.")

    except (Exception, psycopg2.DatabaseError) as error:
        print(f"Error during database setup: {error}")
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    setup_database()
