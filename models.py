### ✅ 1. models.py — Updated with soft and hard deadline fields

from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Date, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import sessionmaker, relationship

Base = declarative_base()
DATABASE_URL = "sqlite:///byZewo.db"
engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(bind=engine)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    email = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)

    jobs = relationship("Job", back_populates="owner", cascade="all, delete")

class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    client_name = Column(String)
    notes = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    image_folder = Column(String)
    final_price = Column(Float, nullable=True)

    # ✅ New deadline fields
    soft_deadline = Column(Date, nullable=True)
    hard_deadline = Column(Date, nullable=True)

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    owner = relationship("User", back_populates="jobs")
    estimates = relationship("Estimate", back_populates="job", cascade="all, delete")
    parts = relationship("Part", back_populates="job", cascade="all, delete")

class Part(Base):
    __tablename__ = "parts"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    width = Column(Float)
    height = Column(Float)
    thickness = Column(String)

    job = relationship("Job", back_populates="parts")

class Estimate(Base):
    __tablename__ = "estimates"
    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    amount = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    job = relationship("Job", back_populates="estimates")

class Stock(Base):
    __tablename__ = "stocks"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)           # e.g., 3/4 Panel, Hinge, etc.
    description = Column(String)                    # e.g., Laminate 2112 White, Soft Close
    quantity = Column(Integer, default=0)
    unit = Column(String, default="pcs")            # e.g., pcs, sheets, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())

