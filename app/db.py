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
        import app.models  # noqa: F401
    except Exception:
        pass
    Base.metadata.create_all(bind=engine)


def seed_default_users():
    """Create default admin and user accounts if they don't exist"""
    from app.models import User
    from app.auth import get_password_hash
    
    db = SessionLocal()
    try:
        # Check if default users already exist
        admin_exists = db.query(User).filter(User.username == "admin").first()
        user_exists = db.query(User).filter(User.username == "user").first()
        
        if not admin_exists:
            print("[INFO] Creating default admin user...")
            admin = User(
                username="admin",
                email="admin@example.com",
                password_hash=get_password_hash("admin123"),
                role="admin",
                is_active=True
            )
            db.add(admin)
        
        if not user_exists:
            print("[INFO] Creating default user...")
            user = User(
                username="user",
                email="user@example.com",
                password_hash=get_password_hash("user123"),
                role="user",
                is_active=True
            )
            db.add(user)
        
        # Add more users here
        test_user_exists = db.query(User).filter(User.username == "testuser").first()
        if not test_user_exists:
            print("[INFO] Creating test user...")
            test_user = User(
                username="testuser",
                email="testuser@example.com",
                password_hash=get_password_hash("testpass123"),
                role="user",
                is_active=True
            )
            db.add(test_user)
        
        db.commit()
        if not admin_exists or not user_exists:
            print("[INFO] Default users created successfully!")
    except Exception as e:
        print(f"[WARNING] Error seeding default users: {e}")
        db.rollback()
    finally:
        db.close()
