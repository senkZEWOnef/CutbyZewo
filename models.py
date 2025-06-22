from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker, relationship

# ✅ Base and Engine
Base = declarative_base()

DATABASE_URL = "sqlite:///byZewo.db"
engine = create_engine(DATABASE_URL, echo=True)

SessionLocal = sessionmaker(bind=engine)

# ✅ User table
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

# ✅ Job table with final_price and estimates relationship
class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    client_name = Column(String)
    notes = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    image_folder = Column(String)
    final_price = Column(Float, nullable=True)  # ✅ NEW

    # Link to estimates
    estimates = relationship("Estimate", back_populates="job", cascade="all, delete")

# ✅ New Estimate table
class Estimate(Base):
    __tablename__ = "estimates"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Backlink to Job
    job = relationship("Job", back_populates="estimates")
