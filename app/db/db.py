from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# MySQL connection string
DATABASE_URL = os.getenv("DATABASE_URL", "mysql+pymysql://root:1234567890@localhost/detect_3soc")

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def init_db():
    # Import models here to register them with Base before create_all
    try:
        import app.db.models  # noqa: F401
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)
