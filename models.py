# models.py

from sqlalchemy import Column, Integer, String, DateTime, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
import datetime

Base = declarative_base()

class Job(Base):
    __tablename__ = 'jobs'

    id = Column(Integer, primary_key=True)
    client_name = Column(String)
    notes = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    image_folder = Column(String)

# ✅ Database setup:
engine = create_engine('sqlite:///byzewo.db', echo=True)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)
