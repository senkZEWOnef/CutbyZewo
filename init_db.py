# init_db.py
from models import Base, engine, SessionLocal, User
from werkzeug.security import generate_password_hash

Base.metadata.create_all(bind=engine)

db = SessionLocal()
# If no admin, add one:
if not db.query(User).filter(User.email == "ralph.ulysse509@gmail.com").first():
    admin = User(
        username="zewo",
        email="ralph.ulysse509@gmail.com",
        hashed_password=generate_password_hash("Poesie509$$$")
    )
    db.add(admin)
    db.commit()
    print("✅ Admin user created.")
else:
    print("Admin already exists.")
db.close()
