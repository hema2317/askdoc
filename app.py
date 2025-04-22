from flask import Flask
from sqlalchemy import create_engine, text
from sqlalchemy.orm import scoped_session, sessionmaker
from urllib.parse import urlparse
import os
import logging
import time
import psycopg2  # For direct connection test

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask
app = Flask(__name__)
app.config.from_mapping(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY", "dev"),
    DATABASE_URL=os.getenv("DATABASE_URL")  # Render provides this
)

# ---------------------------------------------------
# ✅ 1. TEST DIRECT CONNECTION FIRST (Bypass SQLAlchemy)
# ---------------------------------------------------
def test_postgres_connection():
    """Test if we can connect directly to PostgreSQL with SSL."""
    try:
        db_url = urlparse(app.config["DATABASE_URL"])
        
        # Force 'postgresql://' instead of 'postgres://'
        db_url_str = app.config["DATABASE_URL"].replace(
            "postgres://", "postgresql://", 1
        )
        
        conn = psycopg2.connect(
            dbname=db_url.path[1:],
            user=db_url.username,
            password=db_url.password,
            host=db_url.hostname,
            port=db_url.port,
            sslmode="require",  # Enforce SSL
            connect_timeout=5   # Fail fast if DB is unreachable
        )
        conn.close()
        logger.info("✅ Direct PostgreSQL connection successful!")
        return True
    except Exception as e:
        logger.error(f"❌ Direct PostgreSQL connection failed: {e}")
        return False

# ---------------------------------------------------
# ✅ 2. CONFIGURE SQLALCHEMY ENGINE (With SSL Enforcement)
# ---------------------------------------------------
def create_db_engine():
    """Create SQLAlchemy engine with retries and SSL enforcement."""
    max_retries = 3
    retry_delay = 5  # Seconds between retries
    
    # Ensure URL starts with postgresql:// (not postgres://)
    db_url = app.config["DATABASE_URL"].replace(
        "postgres://", "postgresql://", 1
    )
    
    # Add ?sslmode=require if missing
    if "?sslmode=" not in db_url.lower():
        db_url += "?sslmode=require"
    
    for attempt in range(max_retries):
        try:
            engine = create_engine(
                db_url,
                connect_args={
                    "sslmode": "require",
                    "sslrootcert": "/etc/ssl/certs/ca-certificates.crt",
                    "connect_timeout": 10,
                },
                pool_pre_ping=True,  # Checks connection health
                pool_recycle=300,   # Recycle connections every 5 mins
                pool_size=5,        # Minimum connections
                max_overflow=10,    # Max temporary connections
                echo=False          # Disable in production
            )
            
            # Test connection
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            
            logger.info("✅ SQLAlchemy engine connected successfully!")
            return engine
        
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            logger.critical("🚨 Failed to connect to PostgreSQL after retries!")
            raise RuntimeError("Database connection failed.")

# ---------------------------------------------------
# ✅ 3. INITIALIZE DATABASE (With Error Handling)
# ---------------------------------------------------
def init_db():
    """Initialize database connection."""
    if not test_postgres_connection():
        raise RuntimeError("Cannot connect to PostgreSQL (check SSL settings).")
    
    engine = create_db_engine()
    Session = scoped_session(sessionmaker(bind=engine))
    
    # Optional: Create tables if they don't exist
    from sqlalchemy.ext.declarative import declarative_base
    Base = declarative_base()
    Base.metadata.create_all(engine)
    
    return engine, Session

# ---------------------------------------------------
# 🚀 START THE APPLICATION (With Safety Checks)
# ---------------------------------------------------
if __name__ == "__main__":
    try:
        engine, Session = init_db()
        app.run(host="0.0.0.0", port=5000)
    except Exception as e:
        logger.critical(f"🔥 Application failed to start: {e}")
        exit(1)
