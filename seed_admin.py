# seed_admin.py

from models import SessionLocal, User
from werkzeug.security import generate_password_hash

# change these as needed
username = "zewo"
email = "ralph.ulysse509@gmail.com"
password = "Poesie509$$$"

db = SessionLocal()

# Check if exists
existing = db.query(User).filter(User.email == email).first()
if existing:
    print(f"User {email} already exists.")
else:
    hashed = generate_password_hash(password)
    admin = User(username=username, email=email, hashed_password=hashed)
    db.add(admin)
    db.commit()
    print(f"✅ Created admin user: {email} / {password}")

db.close()
