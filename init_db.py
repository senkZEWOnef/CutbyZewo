# init_db.py

from models import Base, engine

if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created in the database.")
